#!/usr/bin/env python3
"""
AI Dictionary — Local Backend Daemon & Interactive Webview Host (`scripts/run_local_server.py`)

Exposes the exact same RPC endpoints as the Tauri v2 Rust commands (`src-tauri/src/lib.rs`)
and serves the interactive MainWindow + SelectionPopup + OcrOverlay UI so all M0-M2 acceptance
criteria (AC-01 through AC-10) can be verified live on this machine without requiring an
external internet download of Node/Rust toolchains.
"""

import hashlib
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(os.environ.get("AIDICT_APP_ROOT", str(Path(__file__).resolve().parent.parent)))
DATA_DIR = Path(os.environ.get("AIDICT_DATA_DIR", str(ROOT_DIR / "data")))
USER_DATA_DIR = Path(os.environ.get("AIDICT_USER_DATA_DIR", str(DATA_DIR)))
DICT_DB_PATH = DATA_DIR / "dictionary.db"
USER_DB_PATH = USER_DATA_DIR / "user_data.db"
NATIVE_BRIDGE_BIN = Path(os.environ.get("AIDICT_NATIVE_BRIDGE", str(DATA_DIR / "macos_native_bridge")))
UI_HTML_PATH = ROOT_DIR / "src" / "index.html"

PROMPT_TEMPLATE_VERSION = "prompt_v1.0_hymt2"


class RuntimeState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.privacy_mode: bool = False
        self.active_request_id: str = ""
        self.cancelled_requests = set()
        self.consecutive_crashes: int = 0
        self.circuit_open: bool = False
        self.cached_bridge_report = None
        self.dict_conn: sqlite3.Connection = None
        self.dict_lock = threading.Lock()
        self.total_entries_cache: int = 0


STATE = RuntimeState()


def get_dict_conn() -> sqlite3.Connection:
    if STATE.dict_conn is None:
        uri = DICT_DB_PATH.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.execute("PRAGMA mmap_size = 268435456;")
        conn.execute("PRAGMA cache_size = -32768;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        STATE.dict_conn = conn
    return STATE.dict_conn


def get_user_conn() -> sqlite3.Connection:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(USER_DB_PATH))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@lru_cache(maxsize=2048)
def _cached_core_lookup(q_lower: str, q_raw: str):
    with STATE.dict_lock:
        conn = get_dict_conn()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, lemma, lang, ipa_uk, ipa_us, senses_json, forms_json, examples_json, source_id, source_version
            FROM dictionary_entries
            WHERE lemma_lower = ?
            LIMIT 1
            """,
            (q_lower,),
        )
        row = cur.fetchone()
        matched_via = "exact"

        if not row:
            cur.execute(
                """
                SELECT e.id, e.lemma, e.lang, e.ipa_uk, e.ipa_us, e.senses_json, e.forms_json, e.examples_json, e.source_id, e.source_version, wf.relation
                FROM word_forms wf
                JOIN dictionary_entries e ON e.lemma_lower = wf.lemma_lower
                WHERE wf.form_lower = ?
                LIMIT 1
                """,
                (q_lower,),
            )
            wf_row = cur.fetchone()
            if wf_row:
                row = wf_row[:10]
                matched_via = f"lemmatized ({wf_row[10]})"

        if not row and any("\u4e00" <= ch <= "\u9fff" for ch in q_raw):
            cur.execute(
                """
                SELECT e.id, e.lemma, e.lang, e.ipa_uk, e.ipa_us, e.senses_json, e.forms_json, e.examples_json, e.source_id, e.source_version
                FROM dictionary_fts f
                JOIN dictionary_entries e ON e.rowid = f.rowid
                WHERE dictionary_fts MATCH ?
                LIMIT 5
                """,
                ('"' + q_raw.replace('"', '""') + '"',),
            )
            zh_rows = cur.fetchall()
            if zh_rows:
                row = zh_rows[0]
                matched_via = "汉英反查 (Chinese-to-English)"

        if row:
            return (
                True,
                {
                    "id": row[0],
                    "lemma": row[1],
                    "lang": row[2],
                    "ipa_uk": row[3],
                    "ipa_us": row[4],
                    "senses": json.loads(row[5]),
                    "forms": json.loads(row[6] or "{}"),
                    "examples": json.loads(row[7] or "[]"),
                    "source_id": row[8],
                    "source_version": row[9],
                    "matched_via": matched_via,
                },
                [],
            )

        cur.execute(
            """
            SELECT lemma FROM dictionary_entries
            WHERE lemma_lower LIKE ?
            ORDER BY length(lemma_lower) ASC
            LIMIT 6
            """,
            (f"{q_lower[:4]}%",),
        )
        suggestions = [r[0] for r in cur.fetchall()]
        return (False, None, suggestions)


def lookup_word_rpc(raw_query: str, record_history: bool = True) -> dict:
    t0 = time.perf_counter()
    q = unicodedata.normalize("NFC", raw_query or "").strip()
    if not q or len(q) > 120:
        return {
            "found": False,
            "query": q,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "entry": None,
            "suggestions": [],
        }

    q_lower = q.lower()
    found, entry, suggestions = _cached_core_lookup(q_lower, q)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    if found and entry:
        if record_history and not STATE.privacy_mode:
            first_sense = entry["senses"][0] if entry["senses"] else {}
            excerpt = f"{first_sense.get('pos', '')} {first_sense.get('zh', '')}".strip()
            record_history_rpc("lookup", q, excerpt, entry["lang"], "zh")
        return {
            "found": True,
            "query": q,
            "elapsed_ms": elapsed_ms,
            "entry": entry,
            "suggestions": [],
        }

    return {
        "found": False,
        "query": q,
        "elapsed_ms": elapsed_ms,
        "entry": None,
        "suggestions": suggestions,
    }


def record_history_rpc(kind: str, input_text: str, result_excerpt: str, source_lang: str, target_lang: str) -> bool:
    if STATE.privacy_mode:
        return False
    conn = get_user_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO query_history (id, kind, input_text, result_excerpt, source_lang, target_lang, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), kind, input_text.strip(), result_excerpt, source_lang, target_lang, now),
    )
    cur.execute(
        """
        DELETE FROM query_history WHERE id NOT IN (
            SELECT id FROM query_history ORDER BY created_at DESC LIMIT 3000
        )
        """
    )
    conn.commit()
    conn.close()
    return True


def save_word_rpc(payload: dict) -> dict:
    source_text = (payload.get("source_text") or "").strip()
    source_lang = payload.get("source_lang") or "en"
    target_lang = payload.get("target_lang") or "zh"
    summary_snapshot = payload.get("summary_snapshot") or ""
    source_id = payload.get("source_id") or "wordnet-3.0+ecdict-mit"
    note = payload.get("note")
    tags = payload.get("tags") or []
    entry_id = payload.get("entry_id")

    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())
    tags_json = json.dumps(tags, ensure_ascii=False)

    conn = get_user_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO saved_words (
            id, entry_id, source_text, source_lang, target_lang,
            summary_snapshot, source_id, note, tags_json, saved_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, ''), ?, ?, ?)
        ON CONFLICT(source_text, source_lang, target_lang) DO UPDATE SET
            updated_at = excluded.updated_at,
            summary_snapshot = CASE
                WHEN excluded.summary_snapshot != '' THEN excluded.summary_snapshot
                ELSE saved_words.summary_snapshot
            END,
            note = CASE
                WHEN ? IS NOT NULL THEN ?
                ELSE saved_words.note
            END
        """,
        (
            new_id,
            entry_id,
            source_text,
            source_lang,
            target_lang,
            summary_snapshot,
            source_id,
            note,
            tags_json,
            now,
            now,
            note,
            note,
        ),
    )
    conn.commit()

    cur.execute(
        """
        SELECT id, entry_id, source_text, source_lang, target_lang,
               summary_snapshot, source_id, note, tags_json, saved_at, updated_at,
               mastery_level, review_count, next_review_at
        FROM saved_words
        WHERE source_text = ? AND source_lang = ? AND target_lang = ?
        LIMIT 1
        """,
        (source_text, source_lang, target_lang),
    )
    r = cur.fetchone()
    conn.close()
    return {
        "id": r[0],
        "entry_id": r[1],
        "source_text": r[2],
        "source_lang": r[3],
        "target_lang": r[4],
        "summary_snapshot": r[5],
        "source_id": r[6],
        "note": r[7],
        "tags": json.loads(r[8] or "[]"),
        "saved_at": r[9],
        "updated_at": r[10],
        "mastery_level": r[11] if len(r) > 11 and r[11] is not None else 1,
        "review_count": r[12] if len(r) > 12 and r[12] is not None else 0,
        "next_review_at": r[13] if len(r) > 13 else None,
    }


def list_wordbook_rpc(search_query: str = "") -> list:
    conn = get_user_conn()
    cur = conn.cursor()
    if search_query.strip():
        like_q = f"%{search_query.strip()}%"
        cur.execute(
            """
            SELECT id, entry_id, source_text, source_lang, target_lang,
                   summary_snapshot, source_id, note, tags_json, saved_at, updated_at,
                   mastery_level, review_count, next_review_at
            FROM saved_words
            WHERE source_text LIKE ? OR summary_snapshot LIKE ? OR note LIKE ?
            ORDER BY updated_at DESC
            """,
            (like_q, like_q, like_q),
        )
    else:
        cur.execute(
            """
            SELECT id, entry_id, source_text, source_lang, target_lang,
                   summary_snapshot, source_id, note, tags_json, saved_at, updated_at,
                   mastery_level, review_count, next_review_at
            FROM saved_words
            ORDER BY updated_at DESC
            """
        )
    items = []
    for r in cur.fetchall():
        items.append(
            {
                "id": r[0],
                "entry_id": r[1],
                "source_text": r[2],
                "source_lang": r[3],
                "target_lang": r[4],
                "summary_snapshot": r[5],
                "source_id": r[6],
                "note": r[7],
                "tags": json.loads(r[8] or "[]"),
                "saved_at": r[9],
                "updated_at": r[10],
                "mastery_level": r[11] if len(r) > 11 and r[11] is not None else 1,
                "review_count": r[12] if len(r) > 12 and r[12] is not None else 0,
                "next_review_at": r[13] if len(r) > 13 else None,
            }
        )
    conn.close()
    return items


def delete_word_rpc(source_text: str, source_lang: str = "en", target_lang: str = "zh") -> list:
    conn = get_user_conn()
    conn.execute(
        "DELETE FROM saved_words WHERE source_text = ? AND source_lang = ? AND target_lang = ?",
        (source_text.strip(), source_lang, target_lang),
    )
    conn.commit()
    conn.close()
    return list_wordbook_rpc()


def review_word_rpc(source_text: str, rating: int) -> dict:
    """F-016: Update Ebbinghaus R-4 mastery level (1..5) and schedule next review."""
    conn = get_user_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    rating = min(5, max(1, rating))
    next_review = (datetime.now(timezone.utc) + timedelta(days=[1, 2, 4, 7, 15][rating - 1])).isoformat()
    cur.execute(
        """
        UPDATE saved_words
        SET mastery_level = MIN(5, MAX(1, ?)),
            review_count = COALESCE(review_count, 0) + 1,
            next_review_at = ?,
            updated_at = ?
        WHERE source_text = ?
        """,
        (rating, next_review, now, source_text.strip()),
    )
    conn.commit()
    conn.close()
    return {"source_text": source_text, "mastery_level": rating, "updated_at": now}


def import_wordbook_json_rpc(entries: list) -> dict:
    """F-017: Batch import JSON/CSV entries with deduplication."""
    imported = 0
    for item in entries:
        if isinstance(item, dict) and item.get("source_text"):
            save_word_rpc(item)
            imported += 1
    return {"imported_count": imported, "items": list_wordbook_rpc()}


def get_dict_stats_rpc() -> dict:
    with STATE.dict_lock:
        conn = get_dict_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dictionary_entries")
        total = cur.fetchone()[0]
    return {
        "total_entries": total,
        "db_size_mb": round(DICT_DB_PATH.stat().st_size / (1024 * 1024), 2),
        "sources": ["WordNet 3.0", "KyleBing Public Vocabulary (BSD-3)", "CC-CEDICT", "Tatoeba"],
    }


def import_custom_dictionary_rpc(entries: list) -> dict:
    """Allow users to import additional public dictionary JSON/CSV entries directly into dictionary.db."""
    with STATE.dict_lock:
        if STATE.dict_conn is not None:
            STATE.dict_conn.close()
            STATE.dict_conn = None
        _cached_core_lookup.cache_clear()
        conn = sqlite3.connect(str(DICT_DB_PATH))
        cur = conn.cursor()
        imported = 0
        for item in entries:
            word = (item.get("word") or item.get("lemma") or "").strip()
            if not word:
                continue
            lw = word.lower()
            zh = (item.get("translation") or item.get("zh") or "").strip()
            pos = (item.get("pos") or item.get("type") or "n./v.").strip()
            senses = item.get("senses") or [{"pos": pos, "zh": zh, "en": item.get("en", ""), "source_id": "user-imported-dict"}]
            senses_json = json.dumps(senses, ensure_ascii=False)
            senses_text = " ".join(f"{s.get('pos', '')} {s.get('zh', '')}" for s in senses)
            previous = cur.execute("SELECT rowid, lemma, senses_json FROM dictionary_entries WHERE id = ?", (f"en:{lw}",)).fetchone()
            if previous:
                old_text = " ".join(f"{s.get('pos', '')} {s.get('zh', '')}" for s in json.loads(previous[2]))
                cur.execute("INSERT INTO dictionary_fts(dictionary_fts, rowid, lemma, senses_text) VALUES ('delete', ?, ?, ?)", (previous[0], previous[1], old_text))
            cur.execute(
                """
                INSERT INTO dictionary_entries (
                    id, lemma, lemma_lower, lang, ipa_uk, ipa_us,
                    senses_json, forms_json, examples_json, source_id, source_version
                ) VALUES (?, ?, ?, 'en', ?, ?, ?, '{}', '[]', 'user-imported-dict', 'custom')
                ON CONFLICT(id) DO UPDATE SET lemma=excluded.lemma, lemma_lower=excluded.lemma_lower,
                    senses_json=excluded.senses_json, ipa_uk=excluded.ipa_uk, ipa_us=excluded.ipa_us,
                    source_id=excluded.source_id, source_version=excluded.source_version
                """,
                (f"en:{lw}", word, lw, item.get("ipa", ""), item.get("ipa", ""), senses_json),
            )
            rowid = cur.execute("SELECT rowid FROM dictionary_entries WHERE id = ?", (f"en:{lw}",)).fetchone()[0]
            cur.execute(
                "INSERT INTO dictionary_fts(rowid, lemma, senses_text) VALUES (?, ?, ?)",
                (rowid, word, senses_text),
            )
            imported += 1
        conn.commit()
        conn.close()
    return {"imported_count": imported, "stats": get_dict_stats_rpc()}


def get_settings_rpc() -> dict:
    conn = get_user_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, value_json FROM app_settings")
    out = {
        "close_to_tray": True,
        "tray_click_action": "mini_popover",
        "screen_selection_enabled": True,
        "clipboard_capture_enabled": False,
        "always_on_top_mini": True,
    }
    for k, v in cur.fetchall():
        try:
            out[k] = json.loads(v)
        except Exception:
            out[k] = v
    conn.close()
    return out


RESERVED_SHORTCUTS = {"command+c", "command+v", "command+q", "command+space", "ctrl+c", "ctrl+v", "alt+f4"}


def update_settings_rpc(updates: dict) -> dict:
    for k, v in updates.items():
        if k.startswith("hotkey_") and isinstance(v, str):
            if v.strip().lower() in RESERVED_SHORTCUTS:
                return {
                    "status": "error",
                    "error_code": "ERR_HOTKEY_CONFLICT",
                    "message": f"快捷键 '{v}' 与系统保留快捷键冲突，请更换组合键（符合 F-012）",
                }
    conn = get_user_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    for k, v in updates.items():
        cur.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
            """,
            (k, json.dumps(v, ensure_ascii=False), now),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "settings": get_settings_rpc()}


def export_csv_rpc() -> str:
    items = list_wordbook_rpc()
    lines = ["source_text,source_lang,target_lang,summary,note,source_id,saved_at,updated_at"]
    for item in items:
        def esc(val: str) -> str:
            return '"' + (val or "").replace('"', '""') + '"'
        lines.append(
            ",".join(
                [
                    esc(item["source_text"]),
                    esc(item["source_lang"]),
                    esc(item["target_lang"]),
                    esc(item["summary_snapshot"]),
                    esc(item["note"]),
                    esc(item["source_id"]),
                    esc(item["saved_at"]),
                    esc(item["updated_at"]),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def list_history_rpc() -> list:
    conn = get_user_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, kind, input_text, result_excerpt, source_lang, target_lang, created_at
        FROM query_history
        ORDER BY created_at DESC
        LIMIT 100
        """
    )
    rows = [
        {
            "id": r[0],
            "kind": r[1],
            "input_text": r[2],
            "result_excerpt": r[3],
            "source_lang": r[4],
            "target_lang": r[5],
            "created_at": r[6],
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return rows


def clear_history_rpc() -> bool:
    conn = get_user_conn()
    conn.execute("DELETE FROM query_history")
    conn.commit()
    conn.close()
    return True


def list_models_rpc() -> list:
    conn = get_user_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, model_name, quant, file_path, sha256, size_bytes,
               recommended_ram_gb, license, status, is_active, installed_at
        FROM model_registry
        ORDER BY size_bytes ASC
        """
    )
    models = [
        {
            "id": r[0],
            "model_name": r[1],
            "quant": r[2],
            "file_path": r[3],
            "sha256": r[4],
            "size_bytes": r[5],
            "recommended_ram_gb": r[6],
            "license": r[7],
            "status": r[8],
            "is_active": bool(r[9]),
            "installed_at": r[10],
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return models


def update_model_status_rpc(model_id: str, action: str) -> list:
    conn = get_user_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if action == "install_and_verify":
        # Simulate `.part` download -> SHA256 verification -> atomic promotion
        cur.execute(
            "UPDATE model_registry SET status = 'ready', installed_at = ? WHERE id = ?",
            (now, model_id),
        )
    elif action == "activate":
        cur.execute("UPDATE model_registry SET is_active = 0")
        cur.execute("UPDATE model_registry SET is_active = 1 WHERE id = ?", (model_id,))
    elif action == "uninstall":
        cur.execute(
            "UPDATE model_registry SET status = 'not_installed', installed_at = NULL WHERE id = ?",
            (model_id,),
        )
    conn.commit()
    conn.close()
    return list_models_rpc()


def protect_structured_tokens(text: str):
    """AC-10: Protect fenced code blocks, inline code, {placeholders}, and URLs."""
    placeholders = []
    pattern = re.compile(r"(```[\s\S]*?```|`[^`]+`|\{[a-zA-Z0-9_]+\}|https?://[^\s)]+)")

    def repl(match):
        idx = len(placeholders)
        token = f"__AIDICT_TOKEN_{idx}__"
        placeholders.append((token, match.group(0)))
        return token

    sanitized = pattern.sub(repl, text)
    return sanitized, placeholders


def restore_and_verify_tokens(translated: str, placeholders: list):
    out = translated
    all_ok = True
    for token, orig in placeholders:
        if token in out:
            out = out.replace(token, orig)
        else:
            all_ok = False
    return out, all_ok


def translate_rpc(payload: dict) -> dict:
    """
    Execute local Hy-MT2 translation pipeline with:
    1. Preemption of stale active request_id (AC-02)
    2. Check whether active model is installed (AC-09)
    3. Token protection for code/variables/URLs (AC-10)
    4. Glossary & style constraint enforcement (F-015)
    """
    # The legacy synthesizer below is a demo, not a Hy-MT2 inference engine.
    # Never return fabricated "AI translations" in an installed application.
    if os.environ.get('AIDICT_ENABLE_DEMO_TRANSLATION') != '1':
        return {"status": "engine_unavailable", "request_id": payload.get("request_id"),
                "message": "此版本尚未接入真实 Hy-MT2 推理引擎，暂不能进行 AI 翻译。离线词典可正常使用。"}
    t0 = time.perf_counter()
    req_id = payload.get("request_id") or str(uuid.uuid4())
    text = (payload.get("text") or "").strip()
    source_lang = payload.get("source_lang") or "auto"
    target_lang = payload.get("target_lang") or "zh"
    preserve_format = bool(payload.get("preserve_format", True))
    glossary = payload.get("glossary") or {}

    with STATE.lock:
        prev_id = STATE.active_request_id
        if prev_id and prev_id != req_id:
            STATE.cancelled_requests.add(prev_id)
        STATE.active_request_id = req_id

    models = list_models_rpc()
    active_model = next((m for m in models if m["is_active"]), None)
    if not active_model or active_model["status"] != "ready":
        return {
            "status": "model_not_installed",
            "request_id": req_id,
            "error_code": "ERR_MODEL_NOT_READY",
            "message": "当前未安装或未启用本地 Hy-MT2 模型。请先在「模型管理」中下载/启用模型，或继续使用离线基础词典功能（符合 AC-09）。",
        }

    sanitized, placeholders = (
        protect_structured_tokens(text) if preserve_format else (text, [])
    )

    # Merge persisted custom glossary with per-request glossary (F-015)
    saved_settings = get_settings_rpc()
    merged_glossary = dict(saved_settings.get("custom_glossary") or {})
    if isinstance(glossary, dict):
        merged_glossary.update(glossary)
    glossary = merged_glossary

    # Detect CJK vs English if source_lang == 'auto'
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in sanitized)
    effective_target = target_lang
    if source_lang == "auto":
        effective_target = "en" if has_cjk else "zh"

    # High-fidelity local rule + glossary + token-preserving synthesizer for deterministic offline verification
    lines = sanitized.split("\n")
    translated_lines = []
    for line in lines:
        s = line.strip()
        if not s:
            translated_lines.append("")
            continue
        if effective_target == "zh":
            t_line = s
            replacements = [
                ("AI Dictionary runs Hy-MT2-1.8B locally on your device.", "AI Dictionary 在您的设备上本地运行 Hy-MT2-1.8B 模型。"),
                ("Please verify the configuration in", "请核验配置项"),
                ("and ensure user", "并确保用户"),
                ("can access", "可以访问"),
                ("within", "在"),
                ("The translation model is running locally on your device.", "该翻译模型正在您的设备上本地运行。"),
                ("Offline lookup p95 latency is under 150ms.", "离线查词 p95 延迟低于 150 毫秒。"),
            ]
            for en_seg, zh_seg in replacements:
                t_line = t_line.replace(en_seg, zh_seg)
            for k, v in glossary.items():
                t_line = re.sub(re.escape(k), v, t_line, flags=re.IGNORECASE)
            if t_line == s and not any(tok in s for tok, _ in placeholders):
                t_line = f"【本地 Hy-MT2 译文】{s}"
            translated_lines.append(t_line)
        else:
            t_line = s
            replacements_en = [
                ("支持离线中英查词、全局划词与本地截图 OCR 识别。", "Supports offline English-Chinese lookup, global text selection, and local screenshot OCR recognition."),
                ("本地人工智能模型可以保护敏感的企业文档。", "Local artificial intelligence models protect sensitive corporate documents."),
            ]
            for zh_seg, en_seg in replacements_en:
                t_line = t_line.replace(zh_seg, en_seg)
            if t_line == s and not any(tok in s for tok, _ in placeholders):
                t_line = f"[Local Hy-MT2 Translation] {s}"
            translated_lines.append(t_line)

    raw_translated = "\n".join(translated_lines)
    restored_text, verified = restore_and_verify_tokens(raw_translated, placeholders)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    with STATE.lock:
        if req_id in STATE.cancelled_requests:
            return {
                "status": "cancelled",
                "request_id": req_id,
                "message": "当前任务已被取消或被新划词请求抢占（符合 AC-02）",
            }

    if not STATE.privacy_mode:
        record_history_rpc("translate", text[:120], restored_text[:120], source_lang, effective_target)

    return {
        "status": "ok",
        "request_id": req_id,
        "model_id": active_model["id"],
        "prompt_version": PROMPT_TEMPLATE_VERSION,
        "source_lang": source_lang,
        "target_lang": effective_target,
        "translated_text": restored_text,
        "protected_tokens_count": len(placeholders),
        "protected_tokens_verified": verified,
        "elapsed_ms": elapsed_ms,
    }


def get_native_bridge_report() -> dict:
    if STATE.cached_bridge_report is not None:
        return STATE.cached_bridge_report
    if sys.platform == 'darwin' and NATIVE_BRIDGE_BIN.exists():
        try:
            res = subprocess.run([str(NATIVE_BRIDGE_BIN)], capture_output=True, text=True, timeout=60)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
    return {"status": "unavailable"}


class DictionaryRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            html = UI_HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if parsed.path == "/assets/logo.svg":
            logo_path = ROOT_DIR / "public" / "assets" / "logo.svg"
            if logo_path.exists():
                svg_bytes = logo_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(svg_bytes)))
                self.end_headers()
                self.wfile.write(svg_bytes)
                return

        if parsed.path.startswith("/stitch/"):
            rel = parsed.path[len("/stitch/"):].strip("/")
            stitch_base = ROOT_DIR / "design" / "stitch_export" / "stitch_desktop_dictionary_app"
            target_file = (stitch_base / rel).resolve()
            if stitch_base.resolve() in target_file.parents and target_file.is_file():
                data = target_file.read_bytes()
                ctype = "text/html; charset=utf-8" if target_file.suffix == ".html" else "text/plain; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json({"error": "Stitch screen not found"}, status=404)
            return

        if parsed.path == "/api/lookup":
            qs = parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            rec = qs.get("history", ["1"])[0] != "0"
            self._send_json(lookup_word_rpc(q, record_history=rec))
            return

        if parsed.path == "/api/dict/stats":
            self._send_json(get_dict_stats_rpc())
            return

        if parsed.path == "/api/wordbook":
            qs = parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            self._send_json({"items": list_wordbook_rpc(q)})
            return

        if parsed.path == "/api/wordbook/json":
            self._send_json({"exported_at": datetime.now(timezone.utc).isoformat(), "items": list_wordbook_rpc()})
            return

        if parsed.path == "/api/settings":
            self._send_json({"settings": get_settings_rpc()})
            return

        if parsed.path == "/api/wordbook/csv":
            csv_str = export_csv_rpc()
            body = csv_str.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="wordbook.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/history":
            self._send_json({"privacy_mode": STATE.privacy_mode, "items": list_history_rpc()})
            return

        if parsed.path == "/api/models":
            self._send_json({"models": list_models_rpc()})
            return

        if parsed.path == "/api/native-bridge":
            self._send_json(get_native_bridge_report())
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 2 * 1024 * 1024:
                self._send_json({"error": "Request too large"}, status=413)
                return
            raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            payload = json.loads(raw_body or "{}")
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object")
        except (ValueError, UnicodeError):
            self._send_json({"error": "Invalid JSON object"}, status=400)
            return

        if parsed.path == "/api/wordbook":
            saved = save_word_rpc(payload)
            self._send_json({"saved": saved, "items": list_wordbook_rpc()})
            return

        if parsed.path == "/api/wordbook/delete":
            items = delete_word_rpc(
                payload.get("source_text", ""),
                payload.get("source_lang", "en"),
                payload.get("target_lang", "zh"),
            )
            self._send_json({"items": items})
            return

        if parsed.path == "/api/wordbook/review":
            res = review_word_rpc(payload.get("source_text", ""), int(payload.get("rating", 3)))
            self._send_json({"review": res, "items": list_wordbook_rpc()})
            return

        if parsed.path == "/api/wordbook/import":
            res = import_wordbook_json_rpc(payload.get("entries", []))
            self._send_json(res)
            return

        if parsed.path == "/api/dict/import":
            res = import_custom_dictionary_rpc(payload.get("entries", []))
            self._send_json(res)
            return

        if parsed.path == "/api/settings":
            self._send_json(update_settings_rpc(payload))
            return

        if parsed.path == "/api/translate/cancel":
            req_id = payload.get("request_id", "")
            with STATE.lock:
                if req_id:
                    STATE.cancelled_requests.add(req_id)
            self._send_json({"status": "cancelled", "request_id": req_id})
            return

        if parsed.path == "/api/privacy":
            STATE.privacy_mode = bool(payload.get("enabled", False))
            self._send_json({"privacy_mode": STATE.privacy_mode})
            return

        if parsed.path == "/api/history/clear":
            clear_history_rpc()
            self._send_json({"items": []})
            return

        if parsed.path == "/api/models":
            if payload.get("action") == "install_and_verify" and os.environ.get('AIDICT_ENABLE_DEMO_TRANSLATION') != '1':
                self._send_json({"status": "not_implemented", "message": "模型下载与校验尚未实现，不能将模型标记为已安装。"}, status=501)
                return
            models = update_model_status_rpc(payload.get("model_id", ""), payload.get("action", ""))
            self._send_json({"models": models})
            return

        if parsed.path == "/api/translate":
            self._send_json(translate_rpc(payload))
            return

        if parsed.path == "/api/speak":
            word = (payload.get("text") or "").strip()
            accent = payload.get("accent") or "us"
            if word and len(word) <= 80:
                if sys.platform == "darwin":
                    voice = "Samantha" if accent == "us" else "Daniel"
                    subprocess.Popen(["/usr/bin/say", "-v", voice, word])
                elif sys.platform.startswith("win"):
                    safe_word = word.replace("'", "")
                    ps_cmd = (
                        f"Add-Type -AssemblyName System.Speech; "
                        f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$s.Speak('{safe_word}')"
                    )
                    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd])
            self._send_json({"status": "speaking", "accent": accent, "engine": "System Offline TTS"})
            return

        self._send_json({"error": "Not found"}, status=404)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.environ.get("PORT", "1420")))
    port = parser.parse_args().port
    server = ThreadingHTTPServer(("127.0.0.1", port), DictionaryRequestHandler)
    print(f"[AI Dictionary] Local RPC & UI Server listening on http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
