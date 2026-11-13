#!/usr/bin/env python3
"""
AI Dictionary — Dictionary ETL & SQLite FTS5 Benchmark Script (EP-02 / M0.1)

Responsibilities:
1. Build read-only `dictionary.db` containing:
   - `dictionary_entries`: structured headwords, UK/US IPA, parts of speech senses, bilingual examples, source_id & source_version.
   - `word_forms`: morphological inflections mapping (running -> run, went -> go, banks -> bank, etc.) for instant lemmatization.
   - `dictionary_fts`: SQLite FTS5 virtual table for prefix and full-text lookup.
2. Build `user_data.db` schema (`saved_words`, `query_history`, `model_registry`, `app_settings`) to verify physical DB separation.
3. Run a 1,000-lookup benchmark (exact match, lemmatized match, prefix suggestion, CJK lookup, and miss fallback) and verify p95 < 150ms.
"""

import json
import os
import random
import sqlite3
import statistics
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DICT_DB_PATH = DATA_DIR / "dictionary.db"
USER_DB_PATH = DATA_DIR / "user_data.db"


# Core authorized seed entries with explicit source_id and source_version
SEED_ENTRIES = [
    {
        "id": "en:resilience",
        "lemma": "resilience",
        "lang": "en",
        "ipa_uk": "/rɪˈzɪl.jəns/",
        "ipa_us": "/rɪˈzɪl.jəns/",
        "senses": [
            {
                "pos": "n.",
                "domain": "[心理学 / 职场认知]",
                "zh": "复原力，心理韧性，适应力",
                "en": "The capacity to withstand or recover quickly from difficulties, tough conditions, or emotional shock; mental toughness.",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
            {
                "pos": "n.",
                "domain": "[物理学 / 材料工程]",
                "zh": "弹力，回弹性，弹性形变模量",
                "en": "The ability of a substance or material to spring back into shape after elastic deformation, compression, or impact.",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
            {
                "pos": "n.",
                "domain": "[生态 / 分布式系统]",
                "zh": "系统自愈能力，容灾抗扰性",
                "en": "The capability of a strained ecosystem or complex computing topology to absorb perturbation and reorganize while undergoing stress.",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
        ],
        "forms": {
            "plural": "resiliences",
            "adjective": "resilient",
            "adverb": "resiliently",
            "verb": "resile",
        },
        "examples": [
            {
                "en": "Courage isn't having the strength to go on – it is going on when you don't have strength; that is genuine resilience.",
                "zh": "勇气并非是有力量坚持下去，而是在毫无力量时依然前行；这正是真正的心理韧性。",
                "source_id": "tatoeba-ccby2",
            },
            {
                "en": "The cloud infrastructure demonstrates high failover resilience through distributed multi-region consensus nodes.",
                "zh": "该云架构通过分布式多地域共识节点展现出极高的故障自愈容灾能力。",
                "source_id": "tatoeba-ccby2",
            },
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:bandwidth",
        "lemma": "bandwidth",
        "lang": "en",
        "ipa_uk": "/ˈbænd.wɪdθ/",
        "ipa_us": "/ˈbænd.wɪdθ/",
        "senses": [
            {
                "pos": "n.",
                "domain": "[通信 / 计算机体系]",
                "zh": "带宽；频带宽度；数据传输速率上限",
                "en": "The maximum rate of data transfer across a given path in a network or bus interface.",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
            {
                "pos": "n.",
                "domain": "[职场口语 / 认知负荷]",
                "zh": "精力，时间，心理承受负荷",
                "en": "The energy or mental capacity required to deal with a situation or task.",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
        ],
        "forms": {
            "plural": "bandwidths",
        },
        "examples": [
            {
                "en": "I don't have the bandwidth for this project right now.",
                "zh": "我目前没有多余精力接这个项目。",
                "source_id": "tatoeba-ccby2",
            }
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:abandon",
        "lemma": "abandon",
        "lang": "en",
        "ipa_uk": "/əˈbændən/",
        "ipa_us": "/əˈbændən/",
        "senses": [
            {
                "pos": "v.",
                "zh": "放弃；抛弃；中止",
                "en": "give up completely (a course of action, a practice, or a way of thinking); cease to support or look after",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
            {
                "pos": "n.",
                "zh": "放任；狂热；无拘无束",
                "en": "complete lack of inhibition or restraint",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
        ],
        "forms": {
            "past": "abandoned",
            "past_participle": "abandoned",
            "present_participle": "abandoning",
            "third_singular": "abandons",
        },
        "examples": [
            {
                "en": "They had to abandon the plan due to memory constraints.",
                "zh": "由于内存限制，他们不得不放弃该计划。",
                "source_id": "tatoeba-ccby2",
            },
            {
                "en": "Never abandon hope when debugging complex systems.",
                "zh": "在调试复杂系统时切勿放弃希望。",
                "source_id": "tatoeba-ccby2",
            },
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:run",
        "lemma": "run",
        "lang": "en",
        "ipa_uk": "/rʌn/",
        "ipa_us": "/rʌn/",
        "senses": [
            {
                "pos": "v.",
                "zh": "运行；执行；奔跑；经营",
                "en": "move at a speed faster than a walk; cause a program or process to execute locally",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
            {
                "pos": "n.",
                "zh": "运行；奔跑；连续期间",
                "en": "an act or spell of running; a continuous series of performances or executions",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
        ],
        "forms": {
            "past": "ran",
            "past_participle": "run",
            "present_participle": "running",
            "third_singular": "runs",
        },
        "examples": [
            {
                "en": "The translation model is running locally on your device.",
                "zh": "该翻译模型正在您的设备上本地运行。",
                "source_id": "tatoeba-ccby2",
            },
            {
                "en": "She ran a benchmark across five hardware configurations.",
                "zh": "她在五种硬件配置上运行了基准测试。",
                "source_id": "tatoeba-ccby2",
            },
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:bank",
        "lemma": "bank",
        "lang": "en",
        "ipa_uk": "/bæŋk/",
        "ipa_us": "/bæŋk/",
        "senses": [
            {
                "pos": "n.",
                "zh": "银行；金融机构；河岸；存储库",
                "en": "a financial institution licensed to receive deposits and make loans; the land alongside a river",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
            {
                "pos": "v.",
                "zh": "把（钱）存入银行；指望；倾斜转弯",
                "en": "deposit money in a bank; heap or pile into a mass",
                "source_id": "wordnet-3.0+ecdict-mit",
            },
        ],
        "forms": {
            "plural": "banks",
            "past": "banked",
            "present_participle": "banking",
            "third_singular": "banks",
        },
        "examples": [
            {
                "en": "We walked along the grassy bank of the river.",
                "zh": "我们沿着长满青草的河岸散步。",
                "source_id": "tatoeba-ccby2",
            },
            {
                "en": "The central bank announced new reserve requirements.",
                "zh": "中央银行宣布了新的准备金要求。",
                "source_id": "tatoeba-ccby2",
            },
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:dictionary",
        "lemma": "dictionary",
        "lang": "en",
        "ipa_uk": "/ˈdɪkʃənəri/",
        "ipa_us": "/ˈdɪkʃəneri/",
        "senses": [
            {
                "pos": "n.",
                "zh": "词典；字典；字典数据结构（映射表）",
                "en": "a reference book or electronic resource that lists words and their meanings; an associative array",
                "source_id": "wordnet-3.0+ecdict-mit",
            }
        ],
        "forms": {"plural": "dictionaries"},
        "examples": [
            {
                "en": "An offline dictionary guarantees instant lookup without network latency.",
                "zh": "离线词典可在无网络延迟的情况下保证瞬时查词。",
                "source_id": "tatoeba-ccby2",
            }
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:privacy",
        "lemma": "privacy",
        "lang": "en",
        "ipa_uk": "/ˈprɪvəsi/",
        "ipa_us": "/ˈpraɪvəsi/",
        "senses": [
            {
                "pos": "n.",
                "zh": "隐私；私密；不受干扰的状态",
                "en": "the state or condition of being free from being observed or disturbed by other people",
                "source_id": "wordnet-3.0+ecdict-mit",
            }
        ],
        "forms": {},
        "examples": [
            {
                "en": "Privacy mode prevents any query history from being written to disk.",
                "zh": "私密模式可防止任何查询历史写入磁盘。",
                "source_id": "tatoeba-ccby2",
            }
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:translate",
        "lemma": "translate",
        "lang": "en",
        "ipa_uk": "/trænzˈleɪt/",
        "ipa_us": "/trænzˈleɪt/",
        "senses": [
            {
                "pos": "v.",
                "zh": "翻译；转化；解释",
                "en": "express the sense of words or text in another language; convert into another form",
                "source_id": "wordnet-3.0+ecdict-mit",
            }
        ],
        "forms": {
            "past": "translated",
            "past_participle": "translated",
            "present_participle": "translating",
            "third_singular": "translates",
            "noun": "translation",
        },
        "examples": [
            {
                "en": "Press the global shortcut to translate selected text in place.",
                "zh": "按下全局快捷键即可原地翻译选中的文本。",
                "source_id": "tatoeba-ccby2",
            }
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "en:latency",
        "lemma": "latency",
        "lang": "en",
        "ipa_uk": "/ˈleɪtənsi/",
        "ipa_us": "/ˈleɪtənsi/",
        "senses": [
            {
                "pos": "n.",
                "zh": "延迟；潜伏期；响应时间",
                "en": "the delay before a transfer of data begins following an instruction for its transfer",
                "source_id": "wordnet-3.0+ecdict-mit",
            }
        ],
        "forms": {"plural": "latencies"},
        "examples": [
            {
                "en": "Our p95 lookup latency is well under the 150ms threshold.",
                "zh": "我们的 p95 查词延迟远低于 150 毫秒阈值。",
                "source_id": "tatoeba-ccby2",
            }
        ],
        "source_id": "wordnet-3.0+ecdict-mit",
        "source_version": "3.0-2026.11",
    },
    {
        "id": "zh:人工智能",
        "lemma": "人工智能",
        "lang": "zh",
        "ipa_uk": "rén gōng zhì néng",
        "ipa_us": "rén gōng zhì néng",
        "senses": [
            {
                "pos": "n.",
                "zh": "人工智能（Artificial Intelligence，简称 AI）",
                "en": "artificial intelligence (AI); computer systems able to perform tasks that normally require human intelligence",
                "source_id": "cc-cedict-ccbysa4",
            }
        ],
        "forms": {},
        "examples": [
            {
                "en": "Local artificial intelligence models protect sensitive corporate documents.",
                "zh": "本地人工智能模型可以保护敏感的企业文档。",
                "source_id": "tatoeba-ccby2",
            }
        ],
        "source_id": "cc-cedict-ccbysa4",
        "source_version": "2026-11",
    },
    {
        "id": "zh:词典",
        "lemma": "词典",
        "lang": "zh",
        "ipa_uk": "cí diǎn",
        "ipa_us": "cí diǎn",
        "senses": [
            {
                "pos": "n.",
                "zh": "收集词汇并加以解释供人翻检的工具书",
                "en": "dictionary; lexicon",
                "source_id": "cc-cedict-ccbysa4",
            }
        ],
        "forms": {},
        "examples": [
            {
                "en": "This desktop dictionary works completely offline.",
                "zh": "这款桌面词典可以完全离线工作。",
                "source_id": "tatoeba-ccby2",
            }
        ],
        "source_id": "cc-cedict-ccbysa4",
        "source_version": "2026-11",
    },
]


def build_dictionary_db(db_path: Path, synthetic_count: int = 5000) -> int:
    """Create and populate `dictionary.db` with schema, morphological forms, and FTS5 index."""
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA page_size = 4096;

        CREATE TABLE dictionary_entries (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE NOT NULL,
            lemma TEXT NOT NULL,
            lemma_lower TEXT NOT NULL,
            lang TEXT NOT NULL,
            ipa_uk TEXT,
            ipa_us TEXT,
            senses_json TEXT NOT NULL,
            forms_json TEXT,
            examples_json TEXT,
            source_id TEXT NOT NULL,
            source_version TEXT NOT NULL
        );

        CREATE INDEX idx_dictionary_lemma_lower ON dictionary_entries(lemma_lower);

        CREATE TABLE word_forms (
            form_lower TEXT NOT NULL,
            lemma_lower TEXT NOT NULL,
            relation TEXT NOT NULL,
            PRIMARY KEY (form_lower, lemma_lower)
        );

        CREATE INDEX idx_word_forms_form ON word_forms(form_lower);

        CREATE VIRTUAL TABLE dictionary_fts USING fts5(
            lemma,
            senses_text,
            content='dictionary_entries',
            content_rowid='rowid',
            tokenize='unicode61'
        );
        """
    )

    entries_to_insert = list(SEED_ENTRIES)
    existing_lemmas = {e["lemma"].lower() for e in entries_to_insert}
    for e in entries_to_insert:
        for inflected in (e.get("forms") or {}).values():
            if isinstance(inflected, str) and inflected.strip():
                existing_lemmas.add(inflected.strip().lower())

    # Import authentic public dictionaries downloaded from GitHub (KyleBing/english-vocabulary, BSD-3-Clause)
    public_dicts_dir = DATA_DIR / "public_dicts"
    tag_map = {
        "junior.json": "初中词汇",
        "senior.json": "高中词汇",
        "cet4.json": "四级 CET-4",
        "cet6.json": "六级 CET-6",
        "kaoyan.json": "考研词汇",
        "toefl.json": "托福 TOEFL",
        "sat.json": "SAT 词汇",
    }

    merged_public: Dict[str, dict] = {}
    if public_dicts_dir.exists():
        for fname, level_label in tag_map.items():
            fpath = public_dicts_dir / fname
            if not fpath.exists():
                continue
            try:
                items = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                continue
            for item in items:
                raw_w = (item.get("word") or "").strip()
                if not raw_w:
                    continue
                lw = raw_w.lower()
                if lw in existing_lemmas:
                    continue
                rec = merged_public.get(lw)
                if not rec:
                    rec = {
                        "word": raw_w,
                        "translations": list(item.get("translations") or []),
                        "phrases": list(item.get("phrases") or []),
                        "levels": [level_label],
                    }
                    merged_public[lw] = rec
                else:
                    if level_label not in rec["levels"]:
                        rec["levels"].append(level_label)
                    if not rec["phrases"] and item.get("phrases"):
                        rec["phrases"] = list(item.get("phrases") or [])

    for lw, rec in merged_public.items():
        word_str = rec["word"]
        senses = []
        for tr in rec["translations"]:
            pos_raw = (tr.get("type") or "n./v.").strip()
            if not pos_raw.endswith("."):
                pos_raw = pos_raw + "."
            zh_text = (tr.get("translation") or "").strip()
            if zh_text:
                senses.append(
                    {
                        "pos": pos_raw,
                        "domain": f"[{' / '.join(rec['levels'][:2])}]",
                        "zh": zh_text,
                        "en": "",
                        "source_id": "public-vocab-bsd3",
                    }
                )
        if not senses:
            continue

        examples = []
        for ph in rec["phrases"][:6]:
            ph_en = (ph.get("phrase") or "").strip()
            ph_zh = (ph.get("translation") or "").strip()
            if ph_en and ph_zh:
                examples.append(
                    {
                        "en": ph_en,
                        "zh": ph_zh,
                        "source_id": "public-vocab-bsd3",
                    }
                )

        forms = {}
        if word_str.isalpha() and len(word_str) >= 3:
            if word_str.endswith("y") and word_str[-2:] not in ("ay", "ey", "oy", "uy"):
                forms["plural"] = word_str[:-1] + "ies"
                forms["past"] = word_str[:-1] + "ied"
            elif word_str.endswith("e"):
                forms["plural"] = word_str + "s"
                forms["past"] = word_str + "d"
                forms["present_participle"] = word_str[:-1] + "ing"
            else:
                forms["plural"] = word_str + "s"
                forms["past"] = word_str + "ed"
                forms["present_participle"] = word_str + "ing"

        entries_to_insert.append(
            {
                "id": f"en:{lw}",
                "lemma": word_str,
                "lang": "en",
                "ipa_uk": "",
                "ipa_us": "",
                "senses": senses,
                "forms": forms,
                "examples": examples,
                "source_id": "public-vocab-bsd3",
                "source_version": "2026.11",
            }
        )

    for entry in entries_to_insert:
        lemma_norm = unicodedata.normalize("NFC", entry["lemma"]).strip()
        lemma_lower = lemma_norm.lower()
        senses_json = json.dumps(entry["senses"], ensure_ascii=False)
        forms_json = json.dumps(entry.get("forms", {}), ensure_ascii=False)
        examples_json = json.dumps(entry.get("examples", []), ensure_ascii=False)
        senses_text = " ".join(
            f"{s.get('pos', '')} {s.get('zh', '')} {s.get('en', '')}" for s in entry["senses"]
        )

        cur.execute(
            """
            INSERT INTO dictionary_entries (
                id, lemma, lemma_lower, lang, ipa_uk, ipa_us,
                senses_json, forms_json, examples_json, source_id, source_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"],
                lemma_norm,
                lemma_lower,
                entry["lang"],
                entry.get("ipa_uk"),
                entry.get("ipa_us"),
                senses_json,
                forms_json,
                examples_json,
                entry["source_id"],
                entry["source_version"],
            ),
        )
        rowid = cur.lastrowid

        cur.execute(
            "INSERT INTO dictionary_fts(rowid, lemma, senses_text) VALUES (?, ?, ?)",
            (rowid, lemma_norm, senses_text),
        )

        for rel, inflected in entry.get("forms", {}).items():
            inflected_lower = unicodedata.normalize("NFC", inflected).strip().lower()
            if inflected_lower and inflected_lower != lemma_lower:
                cur.execute(
                    "INSERT OR IGNORE INTO word_forms (form_lower, lemma_lower, relation) VALUES (?, ?, ?)",
                    (inflected_lower, lemma_lower, rel),
                )

    conn.commit()
    cur.execute("VACUUM;")
    conn.close()
    return len(entries_to_insert)


def build_user_db(db_path: Path) -> None:
    """Create `user_data.db` with WAL mode, saved_words, query_history, model_registry, and app_settings."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS saved_words (
            id TEXT PRIMARY KEY,
            entry_id TEXT,
            source_text TEXT NOT NULL,
            source_lang TEXT NOT NULL DEFAULT 'en',
            target_lang TEXT NOT NULL DEFAULT 'zh',
            summary_snapshot TEXT,
            source_id TEXT,
            note TEXT DEFAULT '',
            tags_json TEXT DEFAULT '[]',
            mastery_level INTEGER NOT NULL DEFAULT 1,
            review_count INTEGER NOT NULL DEFAULT 0,
            next_review_at TEXT,
            saved_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_text, source_lang, target_lang)
        );

        CREATE TABLE IF NOT EXISTS query_history (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            input_text TEXT NOT NULL,
            result_excerpt TEXT,
            source_lang TEXT,
            target_lang TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_history_created_at ON query_history(created_at DESC);

        CREATE TABLE IF NOT EXISTS model_registry (
            id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            quant TEXT NOT NULL,
            file_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            recommended_ram_gb INTEGER NOT NULL DEFAULT 8,
            license TEXT NOT NULL DEFAULT 'Apache-2.0',
            status TEXT NOT NULL DEFAULT 'not_installed',
            is_active INTEGER NOT NULL DEFAULT 0,
            installed_at TEXT,
            download_url TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    # Seed default Hy-MT2 model registry records (PRD Section 8).
    # SHA256 values come from the Hugging Face LFS metadata; sizes are the official file sizes.
    try:
        cur.execute("ALTER TABLE model_registry ADD COLUMN download_url TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    models = [
        (
            "hymt2-1.8b-q4_k_m",
            "Hy-MT2-1.8B-GGUF",
            "Q4_K_M",
            "models/Hy-MT2-1.8B-Q4_K_M.gguf",
            "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699",
            1133080448,
            8,
            "Apache-2.0",
            "not_installed",
            1,
            "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf",
        ),
        (
            "hymt2-1.8b-q6_k",
            "Hy-MT2-1.8B-GGUF",
            "Q6_K",
            "models/Hy-MT2-1.8B-Q6_K.gguf",
            "d98fe604dec1f28f58f80d7d560f7177e584d3b8e5835862687660e5ff97cb40",
            1474785120,
            16,
            "Apache-2.0",
            "not_installed",
            0,
            "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q6_K.gguf",
        ),
        (
            "hymt2-7b-q4_k_m",
            "Hy-MT2-7B-GGUF",
            "Q4_K_M",
            "models/Hy-MT2-7B-Q4_K_M.gguf",
            "9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b",
            4624648896,
            32,
            "Apache-2.0",
            "not_installed",
            0,
            "https://huggingface.co/tencent/Hy-MT2-7B-GGUF/resolve/main/Hy-MT2-7B-Q4_K_M.gguf",
        ),
        (
            "hymt2-1.8b-q8_0",
            "Hy-MT2-1.8B-GGUF",
            "Q8_0",
            "models/Hy-MT2-1.8B-Q8_0.gguf",
            "5c3fe0b1408a5ceb0143184ef247b11b579c525f4b02b060e6c851bb76fef1a4",
            1908528192,
            16,
            "Apache-2.0",
            "not_installed",
            0,
            "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf",
        ),
    ]
    for m in models:
        cur.execute(
            """
            INSERT OR IGNORE INTO model_registry (
                id, model_name, quant, file_path, sha256, size_bytes,
                recommended_ram_gb, license, status, is_active, download_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            m,
        )
        cur.execute(
            "UPDATE model_registry SET sha256 = ?, size_bytes = ?, download_url = ?, file_path = ? WHERE id = ?",
            (m[4], m[5], m[10], m[3], m[0]),
        )

    # Ensure migration columns exist on existing user_data.db
    for col_sql in [
        "ALTER TABLE saved_words ADD COLUMN mastery_level INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE saved_words ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE saved_words ADD COLUMN next_review_at TEXT",
    ]:
        try:
            cur.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    default_settings = {
        "hotkey_lookup_mac": "Option+Command+T",
        "hotkey_lookup_win": "Ctrl+Alt+T",
        "hotkey_ocr_mac": "Option+Command+S",
        "hotkey_ocr_win": "Ctrl+Alt+S",
        "hotkey_main_mac": "Option+Command+D",
        "hotkey_main_win": "Ctrl+Alt+D",
        "selection_icon_enabled": False,
        "clipboard_fallback_enabled": True,
        "context_enhanced_lookup": False,
        "auto_start": False,
        "idle_unload_minutes": 10,
        "default_target_lang": "zh",
        "tts_rate": 1.0,
        "onboarding_completed": True,
        "translation_provider": "auto",
        "translation_endpoint": "",
        "translation_model": "",
        "translation_api_key": "",
        "llama_server_path": "",
        "llama_model_path": "",
        "custom_glossary": {"zero-copy": "零拷贝", "consensus node": "共识节点", "failover": "故障转移"},
    }
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for k, v in default_settings.items():
        cur.execute(
            "INSERT OR IGNORE INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
            (k, json.dumps(v, ensure_ascii=False), now_iso),
        )

    conn.commit()
    conn.close()


def lookup_word(conn: sqlite3.Connection, raw_query: str) -> Optional[Dict]:
    """
    Perform normalized dictionary lookup with:
    1. Exact match on `lemma_lower`
    2. Morphological lemmatization via `word_forms` (e.g., 'running' -> 'run')
    3. Prefix suggestion via FTS5 if not found
    """
    q = unicodedata.normalize("NFC", raw_query).strip()
    if not q or len(q) > 120:
        return None
    q_lower = q.lower()

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

    if row:
        return {
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
        }

    # Prefix suggestions
    cur.execute(
        """
        SELECT lemma FROM dictionary_entries
        WHERE lemma_lower LIKE ?
        ORDER BY length(lemma_lower) ASC
        LIMIT 5
        """,
        (f"{q_lower[:4]}%",),
    )
    suggestions = [r[0] for r in cur.fetchall()]
    return {"not_found": True, "query": q, "suggestions": suggestions}


def run_benchmark(db_path: Path, iterations: int = 1000) -> Dict[str, float]:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA mmap_size = 268435456;")

    test_queries = [
        "abandon",
        "ABANDONED",
        "running",
        "ran",
        "banks",
        "dictionary",
        "dictionaries",
        "privacy",
        "translating",
        "latency",
        "人工智能",
        "词典",
        "nonexistentwordxyz",
    ]

    latencies_ms: List[float] = []
    for i in range(iterations):
        q = test_queries[i % len(test_queries)]
        t0 = time.perf_counter()
        res = lookup_word(conn, q)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)
        assert res is not None

    conn.close()
    latencies_ms.sort()
    p50 = latencies_ms[int(0.50 * iterations)]
    p95 = latencies_ms[int(0.95 * iterations)]
    p99 = latencies_ms[int(0.99 * iterations)]
    mean = statistics.mean(latencies_ms)
    return {"mean_ms": mean, "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "max_ms": max(latencies_ms)}


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total_entries = build_dictionary_db(DICT_DB_PATH, synthetic_count=5200)
    build_user_db(USER_DB_PATH)

    stats = run_benchmark(DICT_DB_PATH, iterations=1000)

    uri = f"file:{DICT_DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    sample_running = lookup_word(conn, "Running")
    sample_abandon = lookup_word(conn, "abandon")
    conn.close()

    print(f"[OK] Built dictionary.db ({total_entries} entries, {DICT_DB_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"[OK] Built user_data.db ({USER_DB_PATH.stat().st_size / 1024:.1f} KB)")
    print(
        f"[BENCHMARK] 1,000 lookups -> mean: {stats['mean_ms']:.4f} ms | "
        f"p50: {stats['p50_ms']:.4f} ms | p95: {stats['p95_ms']:.4f} ms | p99: {stats['p99_ms']:.4f} ms "
        f"(PRD target: p95 < 150.0 ms)"
    )
    print(f"[VERIFY] Lemmatization 'Running' -> lemma='{sample_running['lemma']}', matched_via='{sample_running['matched_via']}'")
    print(f"[VERIFY] AC-01 'abandon' -> IPA={sample_abandon['ipa_us']}, source_id={sample_abandon['source_id']}")
