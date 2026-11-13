#!/usr/bin/env python3
"""
AI Dictionary — Local Backend Daemon & Webview Host (`scripts/run_local_server.py`)

Serves the interactive MainWindow + SelectionPopup + OcrOverlay UI and the local
RPC endpoints used by the Windows and macOS native shells.
"""

import hashlib
import argparse
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
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

PROMPT_TEMPLATE_VERSION = "prompt_v1.1_hymt2"
MODELS_DIR_NAME = "models"
MAX_TRANSLATE_CHARS = 20000
TRANSLATE_CHUNK_CHARS = 1400


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
        self.model_downloads = {}
        self.download_lock = threading.Lock()
        self.translation_proc = None
        self.translation_port = 0
        self.translation_proc_model = ""
        self.translation_lock = threading.Lock()
        self.translation_last_error = ""


STATE = RuntimeState()

MODEL_CATALOG = {
    "hymt2-1.8b-q4_k_m": {
        "file_name": "Hy-MT2-1.8B-Q4_K_M.gguf",
        "size_bytes": 1133080448,
        "sha256": "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699",
        "url": "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf",
    },
    "hymt2-1.8b-q6_k": {
        "file_name": "Hy-MT2-1.8B-Q6_K.gguf",
        "size_bytes": 1474785120,
        "sha256": "d98fe604dec1f28f58f80d7d560f7177e584d3b8e5835862687660e5ff97cb40",
        "url": "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q6_K.gguf",
    },
    "hymt2-1.8b-q8_0": {
        "file_name": "Hy-MT2-1.8B-Q8_0.gguf",
        "size_bytes": 1908528192,
        "sha256": "5c3fe0b1408a5ceb0143184ef247b11b579c525f4b02b060e6c851bb76fef1a4",
        "url": "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf",
    },
    "hymt2-7b-q4_k_m": {
        "file_name": "Hy-MT2-7B-Q4_K_M.gguf",
        "size_bytes": 4624648896,
        "sha256": "9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b",
        "url": "https://huggingface.co/tencent/Hy-MT2-7B-GGUF/resolve/main/Hy-MT2-7B-Q4_K_M.gguf",
    },
}


_MODEL_SCHEMA_READY = False


def models_dir() -> Path:
    path = USER_DATA_DIR / MODELS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_model_schema() -> None:
    """Add download metadata columns to existing user databases and refresh catalog values."""
    global _MODEL_SCHEMA_READY
    if _MODEL_SCHEMA_READY:
        return
    conn = get_user_conn()
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(model_registry)")}
        if "download_url" not in columns:
            conn.execute("ALTER TABLE model_registry ADD COLUMN download_url TEXT DEFAULT ''")
        for model_id, meta in MODEL_CATALOG.items():
            target = models_dir() / meta["file_name"]
            row = conn.execute("SELECT status FROM model_registry WHERE id = ?", (model_id,)).fetchone()
            if row is None:
                continue
            # Preserve installation state, refresh only catalog metadata.
            conn.execute(
                """
                UPDATE model_registry
                SET file_path = ?, sha256 = ?, size_bytes = ?, download_url = ?
                WHERE id = ?
                """,
                (str(target), meta["sha256"], meta["size_bytes"], meta["url"], model_id),
            )
        # Any download that was interrupted by a restart is resumable again.
        conn.execute("UPDATE model_registry SET status = 'not_installed' WHERE status = 'downloading'")
        conn.commit()
    finally:
        conn.close()
    _MODEL_SCHEMA_READY = True


def model_path_for(model_id: str) -> Path:
    meta = MODEL_CATALOG.get(model_id)
    if meta:
        return models_dir() / meta["file_name"]
    conn = get_user_conn()
    try:
        row = conn.execute("SELECT file_path FROM model_registry WHERE id = ?", (model_id,)).fetchone()
        return Path(row[0]) if row and row[0] else models_dir() / f"{model_id}.gguf"
    finally:
        conn.close()


def sha256_file(path: Path, progress=None) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size if path.exists() else 0
    done = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
            done += len(block)
            if progress:
                progress(done, total)
    return digest.hexdigest()


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
        "clipboard_fallback_enabled": True,
        "always_on_top_mini": True,
        "hotkey_lookup_win": "Ctrl+Alt+T",
        "hotkey_lookup_mac": "Option+Command+T",
        "hotkey_ocr_win": "Ctrl+Alt+S",
        "hotkey_ocr_mac": "Option+Command+S",
        "hotkey_main_win": "Ctrl+Alt+D",
        "hotkey_main_mac": "Option+Command+D",
        "translation_provider": "auto",
        "translation_endpoint": "",
        "translation_model": "",
        "translation_api_key": "",
        "llama_server_path": "",
        "llama_model_path": "",
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
    ensure_model_schema()
    conn = get_user_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, model_name, quant, file_path, sha256, size_bytes,
               recommended_ram_gb, license, status, is_active, installed_at, download_url
        FROM model_registry
        ORDER BY size_bytes ASC
        """
    )
    models = []
    for r in cur.fetchall():
        download = STATE.model_downloads.get(r[0])
        status = r[8]
        if download and download.get("status") == "downloading":
            status = "downloading"
        models.append(
            {
                "id": r[0],
                "model_name": r[1],
                "quant": r[2],
                "file_path": r[3],
                "sha256": r[4],
                "size_bytes": r[5],
                "recommended_ram_gb": r[6],
                "license": r[7],
                "status": status,
                "is_active": bool(r[9]),
                "installed_at": r[10],
                "download_url": r[11] or "",
                "downloaded_bytes": (download or {}).get("downloaded", 0),
                "percent": (download or {}).get("percent", 0.0),
                "file_exists": Path(r[3]).is_file() if r[3] else False,
            }
        )
    conn.close()
    return models


def _set_download_state(model_id: str, **fields) -> None:
    with STATE.download_lock:
        state = STATE.model_downloads.setdefault(model_id, {})
        state.update(fields)
        state["updated_at"] = time.time()


def start_model_download(model_id: str) -> dict:
    meta = MODEL_CATALOG.get(model_id)
    if not meta:
        return {"status": "error", "message": "未知的模型。", "model_id": model_id}
    target = model_path_for(model_id)
    if target.is_file() and target.stat().st_size == meta["size_bytes"]:
        actual = sha256_file(target)
        if actual.lower() == meta["sha256"].lower():
            conn = get_user_conn()
            conn.execute(
                "UPDATE model_registry SET status = 'ready', installed_at = COALESCE(installed_at, ?) WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), model_id),
            )
            conn.commit()
            conn.close()
            return {"status": "ready", "message": "模型已存在且校验通过。", "model_id": model_id}
        # Same size but wrong content: remove it and download again.
        try:
            target.unlink()
        except OSError:
            pass

    existing = STATE.model_downloads.get(model_id)
    if existing and existing.get("status") == "downloading":
        return {"status": "downloading", "message": "模型正在下载中。", "model_id": model_id}

    free = shutil.disk_usage(target.parent).free
    if free < meta["size_bytes"] * 1.05:
        return {
            "status": "error",
            "message": f"磁盘空间不足：需要约 {meta['size_bytes'] / (1024 ** 3):.2f} GB，当前仅剩 {free / (1024 ** 3):.2f} GB。",
            "model_id": model_id,
        }

    _set_download_state(
        model_id, status="downloading", downloaded=0, total=meta["size_bytes"],
        percent=0.0, message="准备下载…", error="", started_at=time.time(),
    )
    thread = threading.Thread(target=_download_model_worker, args=(model_id, meta, target), daemon=True)
    thread.start()
    return {"status": "downloading", "message": "已开始下载，支持断点续传。", "model_id": model_id}


def _download_model_worker(model_id: str, meta: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    url = meta["url"]
    expected = meta["sha256"]
    total = meta["size_bytes"]
    try:
        existing = part.stat().st_size if part.exists() else 0
        if existing > total:
            part.unlink(missing_ok=True)
            existing = 0
        if existing < total:
            request = urllib.request.Request(url, headers={"User-Agent": "AI-Dictionary/1.0.3"})
            if existing:
                request.add_header("Range", f"bytes={existing}-")
            with urllib.request.urlopen(request, timeout=60) as response:
                mode = "ab" if existing and response.status == 206 else "wb"
                if mode == "wb":
                    existing = 0
                downloaded = existing
                last_report = 0.0
                with part.open(mode) as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        output.write(block)
                        downloaded += len(block)
                        now = time.time()
                        if now - last_report > 0.5:
                            percent = min(99.0, downloaded * 100.0 / total) if total else 0.0
                            _set_download_state(
                                model_id, status="downloading", downloaded=downloaded, total=total,
                                percent=round(percent, 1),
                                message=f"已下载 {downloaded / 1024 ** 2:.0f} / {total / 1024 ** 2:.0f} MiB",
                            )
                            last_report = now
        _set_download_state(
            model_id, status="downloading", downloaded=total, total=total,
            percent=99.0, message="正在校验 SHA256…",
        )
        actual = sha256_file(part)
        if expected and actual.lower() != expected.lower():
            part.unlink(missing_ok=True)
            _set_download_state(
                model_id, status="error", error="sha256_mismatch",
                message="模型校验失败：SHA256 不匹配，已删除损坏文件，请重试。",
            )
            return
        os.replace(part, target)
        conn = get_user_conn()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE model_registry SET is_active = 0")
        conn.execute(
            "UPDATE model_registry SET status = 'ready', is_active = 1, installed_at = ? WHERE id = ?",
            (now_iso, model_id),
        )
        conn.commit()
        conn.close()
        if STATE.translation_proc_model and STATE.translation_proc_model != str(target):
            _stop_llama_server()
        _set_download_state(
            model_id, status="ready", downloaded=total, total=total, percent=100.0,
            message="模型下载并校验完成，已启用。", sha256=actual,
        )
    except Exception as exc:
        _set_download_state(
            model_id, status="error", error=str(exc),
            message=f"模型下载失败：{exc}（已保留 .part，可重试续传）",
        )


def get_download_status(model_id: str) -> dict:
    state = STATE.model_downloads.get(model_id)
    if not state:
        conn = get_user_conn()
        row = conn.execute("SELECT status FROM model_registry WHERE id = ?", (model_id,)).fetchone()
        conn.close()
        status = row[0] if row else "unknown"
        return {"model_id": model_id, "status": status, "percent": 100.0 if status == "ready" else 0.0, "message": ""}
    return {
        "model_id": model_id,
        "status": state.get("status", ""),
        "downloaded": state.get("downloaded", 0),
        "total": state.get("total", 0),
        "percent": state.get("percent", 0.0),
        "message": state.get("message", ""),
    }


def update_model_status_rpc(model_id: str, action: str) -> list:
    conn = get_user_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if action in ("install_and_verify", "download"):
        conn.close()
        start_model_download(model_id)
        return list_models_rpc()
    if action == "activate":
        cur.execute("UPDATE model_registry SET is_active = 0")
        cur.execute("UPDATE model_registry SET is_active = 1 WHERE id = ?", (model_id,))
        cur.execute("SELECT file_path FROM model_registry WHERE id = ?", (model_id,))
        row = cur.fetchone()
        if row and STATE.translation_proc_model and STATE.translation_proc_model != row[0]:
            _stop_llama_server()
    elif action == "uninstall":
        cur.execute("SELECT file_path FROM model_registry WHERE id = ?", (model_id,))
        row = cur.fetchone()
        path = Path(row[0]) if row and row[0] else model_path_for(model_id)
        if STATE.translation_proc_model and Path(STATE.translation_proc_model) == path:
            _stop_llama_server()
        for candidate in (path, path.with_suffix(path.suffix + ".part")):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass
        cur.execute(
            "UPDATE model_registry SET status = 'not_installed', installed_at = NULL, is_active = 0 WHERE id = ?",
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


def _normalize_openai_base(endpoint: str) -> str:
    endpoint = (endpoint or "").strip().rstrip("/")
    if not endpoint:
        return ""
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    if not endpoint.endswith("/v1"):
        endpoint += "/v1"
    return endpoint


def _http_json(url: str, payload=None, api_key: str = "", timeout: float = 30.0):
    data = None
    headers = {"Accept": "application/json", "User-Agent": "AI-Dictionary/1.0.3"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


def _translation_config(overrides=None) -> dict:
    settings = get_settings_rpc()
    config = {
        "provider": os.environ.get("AIDICT_TRANSLATION_PROVIDER") or settings.get("translation_provider") or "auto",
        "endpoint": os.environ.get("AIDICT_OPENAI_ENDPOINT") or settings.get("translation_endpoint") or "",
        "model": os.environ.get("AIDICT_TRANSLATION_MODEL") or settings.get("translation_model") or "",
        "api_key": os.environ.get("AIDICT_OPENAI_API_KEY") or settings.get("translation_api_key") or "",
        "llama_server_path": os.environ.get("AIDICT_LLAMA_SERVER") or settings.get("llama_server_path") or "",
        "llama_model_path": os.environ.get("AIDICT_LLAMA_MODEL") or settings.get("llama_model_path") or "",
    }
    if isinstance(overrides, dict):
        for key in ("provider", "endpoint", "model", "api_key", "llama_server_path", "llama_model_path"):
            value = overrides.get(key)
            if value is not None and str(value).strip() != "":
                config[key] = str(value).strip()
    return config


def _active_model_record():
    conn = get_user_conn()
    try:
        row = conn.execute(
            """
            SELECT id, model_name, quant, file_path, sha256, size_bytes, status, is_active
            FROM model_registry
            WHERE is_active = 1 AND status = 'ready'
            ORDER BY installed_at DESC LIMIT 1
            """
        ).fetchone()
        if not row:
            row = conn.execute(
                """
                SELECT id, model_name, quant, file_path, sha256, size_bytes, status, is_active
                FROM model_registry
                WHERE status = 'ready'
                ORDER BY installed_at DESC LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "model_name": row[1], "quant": row[2], "file_path": row[3],
            "sha256": row[4], "size_bytes": row[5], "status": row[6], "is_active": bool(row[7]),
        }
    finally:
        conn.close()


def _find_llama_server(config: dict) -> str:
    candidates = []
    for candidate in (
        config.get("llama_server_path"),
        str(ROOT_DIR / "llama" / "llama-server.exe"),
        str(ROOT_DIR / "llama" / "llama-server"),
        str(ROOT_DIR / "app" / "llama" / "llama-server.exe"),
        str(Path(sys.executable).parent / "llama" / "llama-server.exe"),
        str(Path(sys.executable).parent / "llama" / "llama-server"),
        str(USER_DATA_DIR / "llama" / "llama-server.exe"),
        str(USER_DATA_DIR / "llama" / "llama-server"),
        shutil.which("llama-server"),
    ):
        if candidate:
            candidates.append(candidate)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return str(path)
    return ""


def _resolve_llama_model(config: dict):
    configured = config.get("llama_model_path")
    if configured and Path(configured).is_file():
        return Path(configured), _active_model_record()
    record = _active_model_record()
    if record:
        path = Path(record["file_path"])
        if path.is_file():
            return path, record
        catalog = MODEL_CATALOG.get(record["id"])
        if catalog:
            fallback = models_dir() / catalog["file_name"]
            if fallback.is_file():
                return fallback, record
    return None, record


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _llama_health(port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _stop_llama_server() -> None:
    proc = STATE.translation_proc
    STATE.translation_proc = None
    STATE.translation_port = 0
    STATE.translation_proc_model = ""
    if proc is not None:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
        except Exception:
            pass
    handle = getattr(STATE, "translation_log_handle", None)
    if handle is not None:
        try:
            handle.close()
        except Exception:
            pass
        STATE.translation_log_handle = None


def _physical_threads() -> int:
    """Use physical cores (SMT oversubscription was measured ~40% slower for tg)."""
    logical = os.cpu_count() or 4
    if sys.platform == "darwin":
        try:
            output = subprocess.check_output(["sysctl", "-n", "hw.physicalcpu"], text=True, timeout=2)
            physical = int(output.strip())
            return max(1, min(8, physical))
        except Exception:
            return max(1, min(8, logical))
    if logical <= 4:
        return logical
    return max(2, min(8, logical // 2))


def _start_llama_server(config: dict):
    """Start a loopback-only llama-server for the active GGUF model, reusing a live process."""
    with STATE.translation_lock:
        binary = _find_llama_server(config)
        model_path, record = _resolve_llama_model(config)
        if not binary:
            return None, "未找到 llama-server 可执行文件。请将 llama.cpp 解压到应用目录下的 llama/ 文件夹，或在设置中填写路径。"
        if model_path is None:
            return None, "未找到已安装的 Hy-MT2 模型文件。请先在「本地翻译模型」中下载模型。"
        if STATE.translation_proc is not None and STATE.translation_proc.poll() is None:
            if STATE.translation_proc_model == str(model_path) and _llama_health(STATE.translation_port):
                return STATE.translation_port, ""
            _stop_llama_server()

        port = _free_port()
        log_path = USER_DATA_DIR / "llama-server.log"
        try:
            log_handle = open(log_path, "ab")
        except OSError:
            log_handle = subprocess.DEVNULL
        threads = _physical_threads()
        model_size_gb = model_path.stat().st_size / (1024 ** 3)
        load_mode = "mlock" if model_size_gb < 3.0 and sys.platform != "darwin" else "mmap"
        args = [
            binary, "-m", str(model_path), "--host", "127.0.0.1", "--port", str(port),
            "-c", "3072", "-t", str(threads), "-tb", str(threads),
            "-b", "512", "-ub", "512", "-fa", "on", "-lm", load_mode,
            "-np", "1", "--no-webui",
        ]
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            args, stdout=log_handle, stderr=subprocess.STDOUT,
            creationflags=creationflags, close_fds=not sys.platform.startswith("win"),
        )
        deadline = time.time() + 150
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if _llama_health(port, timeout=1.0):
                STATE.translation_proc = proc
                STATE.translation_port = port
                STATE.translation_proc_model = str(model_path)
                STATE.translation_log_handle = log_handle
                STATE.translation_last_error = ""
                return port, ""
            time.sleep(0.5)
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        try:
            if log_handle is not subprocess.DEVNULL:
                log_handle.close()
        except Exception:
            pass
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-1200:]
        except Exception:
            pass
        STATE.translation_last_error = "llama-server 启动失败。" + (f" 日志：{tail}" if tail else "")
        return None, STATE.translation_last_error


def _target_language_name(code: str) -> str:
    return {"zh": "Simplified Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"}.get(code, code)


def _source_language_name(code: str) -> str:
    return {"zh": "Chinese", "en": "English", "auto": "the source language"}.get(code, code)


def _build_messages(text: str, source_lang: str, target_lang: str, glossary: dict, style: str = "") -> list:
    target_name = _target_language_name(target_lang)
    source_name = _source_language_name(source_lang)
    system = (
        f"You are a professional translator. Translate the user's text from {source_name} to {target_name}. "
        "Output only the translation. Do not add explanations, quotes, markdown fences, or notes. "
        "Preserve numbers, names, code, placeholders, URLs and line breaks exactly."
    )
    if style == "technical":
        system += " Use precise technical terminology and keep a professional tone."
    elif style == "business":
        system += " Use concise, natural business language."
    if glossary:
        pairs = "; ".join(f"{key} => {value}" for key, value in glossary.items())
        system += f" Mandatory glossary: {pairs}."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]


def _openai_chat(config: dict, messages: list, model: str = "", timeout: float = 180.0) -> str:
    base = _normalize_openai_base(config.get("endpoint", ""))
    if not base:
        raise RuntimeError("未配置 OpenAI 兼容地址")
    chosen_model = model or config.get("model") or ""
    if not chosen_model:
        models = _http_json(base + "/models", api_key=config.get("api_key", ""), timeout=10.0)
        rows = models.get("data") or []
        if rows:
            chosen_model = rows[0].get("id") or ""
    payload = {
        "model": chosen_model,
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
        "max_tokens": 4096,
    }
    response = _http_json(base + "/chat/completions", payload, config.get("api_key", ""), timeout=timeout)
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("翻译服务没有返回结果")
    message = choices[0].get("message") or {}
    content = message.get("content") or choices[0].get("text") or ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    content = (content or "").strip()
    if not content:
        raise RuntimeError("翻译服务返回了空结果")
    return content


def _probe_openai(config: dict) -> dict:
    base = _normalize_openai_base(config.get("endpoint", ""))
    if not base:
        return {"ready": False, "message": "尚未填写 OpenAI 兼容地址，例如 http://127.0.0.1:11434/v1。"}
    try:
        models = _http_json(base + "/models", api_key=config.get("api_key", ""), timeout=8.0)
        rows = models.get("data") or []
        names = [str(row.get("id") or "") for row in rows if isinstance(row, dict)]
        chosen = config.get("model") or (names[0] if names else "")
        return {
            "ready": True,
            "model": chosen,
            "endpoint": base,
            "message": f"已连接本地翻译服务{f'（{chosen}）' if chosen else ''}。",
        }
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"ready": False, "message": "本地翻译服务拒绝了 API Key（401/403）。"}
        return {"ready": False, "message": f"本地翻译服务返回 HTTP {exc.code}。"}
    except Exception as exc:
        return {"ready": False, "message": f"无法连接本地翻译服务：{exc}"}


def _probe_llama(config: dict) -> dict:
    binary = _find_llama_server(config)
    model_path, record = _resolve_llama_model(config)
    if not binary:
        return {
            "ready": False,
            "message": "未找到 llama-server。请将 llama.cpp 的 llama/ 文件夹放到应用目录，或在设置中填写 llama-server 路径。",
        }
    if model_path is None:
        return {"ready": False, "message": "尚未安装 Hy-MT2 模型，请先在「本地翻译模型」中下载。"}
    hint = ""
    if record and record.get("quant") in ("Q6_K", "Q8_0", "Q4_K_M") and record.get("quant") != "Q4_K_M":
        hint = " 当前量化更偏质量，速度较慢；日常建议 Q4_K_M（实测约快 1.5–2 倍）。"
    return {
        "ready": True,
        "model": record["id"] if record else model_path.name,
        "model_path": str(model_path),
        "binary": binary,
        "message": "本地 Hy-MT2 模型与推理程序已就绪；首次翻译会自动加载模型（可能需要数秒）。" + hint,
    }


def translation_status() -> dict:
    config = _translation_config()
    provider = config.get("provider") or "auto"
    loaded = bool(
        STATE.translation_proc is not None
        and STATE.translation_proc.poll() is None
        and STATE.translation_port
        and _llama_health(STATE.translation_port)
    )
    if provider == "openai":
        probe = _probe_openai(config)
        probe.update({"provider": "openai", "endpoint": _normalize_openai_base(config.get("endpoint", "")), "model": probe.get("model") or config.get("model", ""), "loaded": loaded})
        return probe
    if provider == "llama":
        probe = _probe_llama(config)
        probe.update({"provider": "llama", "model": probe.get("model") or config.get("model", ""), "loaded": loaded})
        return probe
    # auto: prefer a configured local OpenAI-compatible service, then Hy-MT2.
    if _normalize_openai_base(config.get("endpoint", "")):
        probe = _probe_openai(config)
        if probe.get("ready"):
            probe.update({"provider": "openai", "endpoint": _normalize_openai_base(config.get("endpoint", "")), "loaded": True})
            return probe
    probe = _probe_llama(config)
    probe.update({"provider": "llama", "model": probe.get("model") or config.get("model", ""), "loaded": loaded})
    if not probe.get("ready"):
        probe["message"] = (
            probe.get("message", "")
            + " 也可以连接本机 Ollama / LM Studio 等 OpenAI 兼容服务。"
        ).strip()
    return probe


def preload_translation() -> dict:
    """Load the active Hy-MT2 model before the first translation to remove cold-start latency."""
    config = _translation_config()
    if (config.get("provider") or "auto") == "openai" and _normalize_openai_base(config.get("endpoint", "")):
        probe = _probe_openai(config)
        probe["loaded"] = bool(probe.get("ready"))
        return probe
    port, error = _start_llama_server(config)
    if not port:
        return {"ready": False, "loaded": False, "message": error or "无法预加载本地模型。"}
    return {"ready": True, "loaded": True, "provider": "llama", "message": "本地模型已加载，后续翻译无需等待冷启动。"}


def test_translation_config(overrides: dict) -> dict:
    config = _translation_config(overrides)
    provider = config.get("provider") or "auto"
    if provider in ("openai", "auto") and _normalize_openai_base(config.get("endpoint", "")):
        probe = _probe_openai(config)
        probe["provider"] = "openai"
        return probe
    if provider in ("llama", "auto"):
        probe = _probe_llama(config)
        probe["provider"] = "llama"
        if probe.get("ready") and provider == "llama":
            port, error = _start_llama_server(config)
            if port:
                probe["message"] = "llama-server 已成功启动，可以开始翻译。"
            else:
                probe["ready"] = False
                probe["message"] = error
        return probe
    return {"ready": False, "message": "未知的翻译引擎模式。"}


def _split_text(text: str, limit: int = TRANSLATE_CHUNK_CHARS) -> list:
    paragraphs = re.split(r"(\n\s*\n)", text)
    chunks = []
    buffer = ""
    for part in paragraphs:
        if not part:
            continue
        if len(buffer) + len(part) <= limit:
            buffer += part
            continue
        if buffer.strip():
            chunks.append(buffer)
        buffer = ""
        if len(part) <= limit:
            buffer = part
            continue
        # Split an oversized paragraph at sentence boundaries first, then hard-wrap.
        sentences = re.split(r"(?<=[。！？.!?])\s+", part)
        for sentence in sentences:
            if not sentence:
                continue
            if len(buffer) + len(sentence) + 1 <= limit:
                buffer += (" " if buffer and not buffer.endswith("\n") else "") + sentence
            else:
                if buffer.strip():
                    chunks.append(buffer)
                buffer = ""
                while len(sentence) > limit:
                    chunks.append(sentence[:limit])
                    sentence = sentence[limit:]
                buffer = sentence
    if buffer.strip():
        chunks.append(buffer)
    return chunks or [text]


def _translate_with_provider(config: dict, text: str, source_lang: str, target_lang: str,
                             glossary: dict, style: str, request_id: str) -> dict:
    provider = config.get("provider") or "auto"
    use_openai = provider == "openai" or (provider == "auto" and _normalize_openai_base(config.get("endpoint", "")))
    last_error = ""
    if use_openai:
        try:
            messages = _build_messages(text, source_lang, target_lang, glossary, style)
            result = _openai_chat(config, messages, timeout=180.0)
            return {"ok": True, "provider": "openai", "text": result, "model": config.get("model", "")}
        except Exception as exc:
            last_error = f"OpenAI 兼容服务翻译失败：{exc}"
            if provider == "openai":
                return {"ok": False, "provider": "openai", "message": last_error}
    # Hy-MT2 via llama-server
    port, error = _start_llama_server(config)
    if not port:
        return {"ok": False, "provider": "llama", "message": error or last_error or "本地翻译引擎不可用"}
    model_config = dict(config)
    model_config["endpoint"] = f"http://127.0.0.1:{port}/v1"
    model_config["api_key"] = ""
    messages = _build_messages(text, source_lang, target_lang, glossary, style)
    try:
        result = _openai_chat(model_config, messages, model=config.get("model", ""), timeout=300.0)
        record = _active_model_record()
        return {
            "ok": True,
            "provider": "llama",
            "text": result,
            "model": (record or {}).get("id", ""),
            "port": port,
        }
    except Exception as exc:
        return {"ok": False, "provider": "llama", "message": f"本地 Hy-MT2 翻译失败：{exc}"}


def translate_rpc(payload: dict) -> dict:
    """
    Translate with the configured local provider:
    - Hy-MT2 through a loopback llama-server sidecar
    - any OpenAI-compatible local service (Ollama / LM Studio / vLLM)
    Applies request preemption, long-text chunking, glossary/style constraints and
    code/URL/placeholder protection.
    """
    t0 = time.perf_counter()
    req_id = payload.get("request_id") or str(uuid.uuid4())
    text = (payload.get("text") or "").strip()
    source_lang = payload.get("source_lang") or "auto"
    target_lang = payload.get("target_lang") or "zh"
    preserve_format = bool(payload.get("preserve_format", True))
    style = payload.get("style") or ""
    glossary = payload.get("glossary") or {}

    if not text:
        return {"status": "empty", "request_id": req_id, "message": "请先输入或粘贴要翻译的文本。"}
    if len(text) > MAX_TRANSLATE_CHARS:
        return {
            "status": "too_long", "request_id": req_id,
            "message": f"单次翻译最多支持 {MAX_TRANSLATE_CHARS} 个字符，请分段翻译。",
        }

    with STATE.lock:
        prev_id = STATE.active_request_id
        if prev_id and prev_id != req_id:
            STATE.cancelled_requests.add(prev_id)
        STATE.active_request_id = req_id

    # Merge persisted glossary with per-request glossary (F-015).
    saved_settings = get_settings_rpc()
    merged_glossary = dict(saved_settings.get("custom_glossary") or {})
    if isinstance(glossary, dict):
        merged_glossary.update({str(k): str(v) for k, v in glossary.items() if k and v})

    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in text)
    effective_target = target_lang
    if source_lang == "auto":
        effective_target = "en" if has_cjk else "zh"
        source_lang = "zh" if has_cjk else "en"

    config = _translation_config()
    chunks = _split_text(text)
    translated_chunks = []
    placeholders_count = 0
    tokens_verified = True
    for index, chunk in enumerate(chunks):
        with STATE.lock:
            if req_id in STATE.cancelled_requests:
                return {
                    "status": "cancelled", "request_id": req_id,
                    "message": "当前任务已被取消或被新划词请求抢占。",
                }
        sanitized, placeholders = protect_structured_tokens(chunk) if preserve_format else (chunk, [])
        placeholders_count += len(placeholders)
        result = _translate_with_provider(
            config, sanitized, source_lang, effective_target, merged_glossary, style, req_id
        )
        if not result.get("ok"):
            return {
                "status": "engine_unavailable",
                "request_id": req_id,
                "error_code": "ERR_TRANSLATION_ENGINE",
                "provider": result.get("provider", ""),
                "message": result.get("message") or "本地翻译引擎不可用。",
            }
        restored, verified = restore_and_verify_tokens(result["text"], placeholders)
        tokens_verified = tokens_verified and verified
        translated_chunks.append(restored)

    restored_text = "\n".join(translated_chunks)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    with STATE.lock:
        if req_id in STATE.cancelled_requests:
            return {
                "status": "cancelled",
                "request_id": req_id,
                "message": "当前任务已被取消或被新划词请求抢占。",
            }
        if STATE.active_request_id == req_id:
            STATE.active_request_id = ""

    if not STATE.privacy_mode:
        record_history_rpc("translate", text[:120], restored_text[:120], source_lang, effective_target)

    return {
        "status": "ok",
        "request_id": req_id,
        "provider": result.get("provider", ""),
        "model_id": result.get("model", ""),
        "model": result.get("model", ""),
        "prompt_version": PROMPT_TEMPLATE_VERSION,
        "source_lang": source_lang,
        "target_lang": effective_target,
        "translated_text": restored_text,
        "protected_tokens_count": placeholders_count,
        "protected_tokens_verified": tokens_verified,
        "chunks": len(chunks),
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

        if parsed.path == "/api/models/download/status":
            qs = parse_qs(parsed.query)
            model_id = qs.get("model_id", [""])[0]
            self._send_json(get_download_status(model_id))
            return

        if parsed.path == "/api/translate/status":
            self._send_json(translation_status())
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
            model_id = payload.get("model_id", "")
            action = payload.get("action", "")
            if action in ("install_and_verify", "download"):
                started = start_model_download(model_id)
                self._send_json({"status": started.get("status", "downloading"), **started, "models": list_models_rpc()})
                return
            models = update_model_status_rpc(model_id, action)
            self._send_json({"models": models})
            return

        if parsed.path == "/api/models/download":
            started = start_model_download(payload.get("model_id", ""))
            status = 409 if started.get("status") == "error" else 200
            self._send_json(started, status=status)
            return

        if parsed.path == "/api/translate/test":
            result = test_translation_config(payload)
            self._send_json(result)
            return

        if parsed.path == "/api/translate/preload":
            self._send_json(preload_translation())
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
    ensure_model_schema()
    server = ThreadingHTTPServer(("127.0.0.1", port), DictionaryRequestHandler)
    print(f"[AI Dictionary] Local RPC & UI Server listening on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        _stop_llama_server()
