// EP-09: Wordbook & Query History Repository (`user_data.db`)
// Enforces:
// - AC-07: Privacy Mode Guard (zero disk writes to query_history when privacy_mode is enabled)
// - AC-08: UNIQUE(source_text, source_lang, target_lang) upsert preserving existing user notes
// - F-009: CSV export without hidden analytics copies

use chrono::Utc;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SavedWord {
    pub id: String,
    pub entry_id: Option<String>,
    pub source_text: String,
    pub source_lang: String,
    pub target_lang: String,
    pub summary_snapshot: String,
    pub source_id: String,
    pub note: String,
    pub tags: Vec<String>,
    pub saved_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryHistoryItem {
    pub id: String,
    pub kind: String,
    pub input_text: String,
    pub result_excerpt: String,
    pub source_lang: String,
    pub target_lang: String,
    pub created_at: String,
}

pub struct UserDataRepository {
    conn: Mutex<Connection>,
    privacy_mode: AtomicBool,
}

impl UserDataRepository {
    pub fn new(db_path: &Path) -> Result<Self, String> {
        let conn = Connection::open(db_path)
            .map_err(|e| format!("Failed to open user_data.db: {}", e))?;
        let _ = conn.execute_batch("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");
        Ok(Self {
            conn: Mutex::new(conn),
            privacy_mode: AtomicBool::new(false),
        })
    }

    pub fn set_privacy_mode(&self, enabled: bool) {
        self.privacy_mode.store(enabled, Ordering::SeqCst);
    }

    pub fn is_privacy_mode(&self) -> bool {
        self.privacy_mode.load(Ordering::SeqCst)
    }

    /// Upsert word into wordbook.
    /// AC-08: If (source_text, source_lang, target_lang) already exists, update `updated_at`
    /// while preserving existing non-empty `note` unless the caller explicitly provides a new note.
    pub fn save_word(
        &self,
        entry_id: Option<&str>,
        source_text: &str,
        source_lang: &str,
        target_lang: &str,
        summary_snapshot: &str,
        source_id: &str,
        note: Option<&str>,
        tags: &[String],
    ) -> Result<SavedWord, String> {
        let conn = self.conn.lock().map_err(|_| "Mutex poisoned".to_string())?;
        let now = Utc::now().to_rfc3339();
        let new_id = Uuid::new_v4().to_string();
        let tags_json = serde_json::to_string(tags).unwrap_or_else(|_| "[]".to_string());

        conn.execute(
            "INSERT INTO saved_words (
                id, entry_id, source_text, source_lang, target_lang,
                summary_snapshot, source_id, note, tags_json, saved_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, COALESCE(?8, ''), ?9, ?10, ?10)
             ON CONFLICT(source_text, source_lang, target_lang) DO UPDATE SET
                updated_at = excluded.updated_at,
                summary_snapshot = excluded.summary_snapshot,
                note = CASE
                    WHEN ?8 IS NOT NULL AND ?8 != '' THEN ?8
                    ELSE saved_words.note
                END",
            params![
                new_id,
                entry_id,
                source_text.trim(),
                source_lang,
                target_lang,
                summary_snapshot,
                source_id,
                note,
                tags_json,
                now
            ],
        )
        .map_err(|e| e.to_string())?;

        let mut stmt = conn
            .prepare(
                "SELECT id, entry_id, source_text, source_lang, target_lang,
                        summary_snapshot, source_id, note, tags_json, saved_at, updated_at
                 FROM saved_words
                 WHERE source_text = ?1 AND source_lang = ?2 AND target_lang = ?3
                 LIMIT 1",
            )
            .map_err(|e| e.to_string())?;

        stmt.query_row(params![source_text.trim(), source_lang, target_lang], |row| {
            let tags_str: String = row.get(8).unwrap_or_else(|_| "[]".to_string());
            Ok(SavedWord {
                id: row.get(0)?,
                entry_id: row.get(1).ok(),
                source_text: row.get(2)?,
                source_lang: row.get(3)?,
                target_lang: row.get(4)?,
                summary_snapshot: row.get(5).unwrap_or_default(),
                source_id: row.get(6).unwrap_or_default(),
                note: row.get(7).unwrap_or_default(),
                tags: serde_json::from_str(&tags_str).unwrap_or_default(),
                saved_at: row.get(9)?,
                updated_at: row.get(10)?,
            })
        })
        .map_err(|e| e.to_string())
    }

    /// Record query history ONLY when Privacy Mode is off (AC-07).
    pub fn record_history(
        &self,
        kind: &str,
        input_text: &str,
        result_excerpt: &str,
        source_lang: &str,
        target_lang: &str,
    ) -> Result<bool, String> {
        if self.is_privacy_mode() {
            return Ok(false);
        }

        let conn = self.conn.lock().map_err(|_| "Mutex poisoned".to_string())?;
        let id = Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();

        conn.execute(
            "INSERT INTO query_history (id, kind, input_text, result_excerpt, source_lang, target_lang, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![id, kind, input_text.trim(), result_excerpt, source_lang, target_lang, now],
        )
        .map_err(|e| e.to_string())?;

        // Enforce 3,000 max history cap per PRD Section 6.6
        let _ = conn.execute(
            "DELETE FROM query_history WHERE id NOT IN (
                SELECT id FROM query_history ORDER BY created_at DESC LIMIT 3000
             )",
            [],
        );

        Ok(true)
    }

    /// Export saved words as RFC 4180 CSV string (F-009).
    pub fn export_wordbook_csv(&self) -> Result<String, String> {
        let conn = self.conn.lock().map_err(|_| "Mutex poisoned".to_string())?;
        let mut stmt = conn
            .prepare(
                "SELECT source_text, source_lang, target_lang, summary_snapshot, note, source_id, saved_at, updated_at
                 FROM saved_words
                 ORDER BY updated_at DESC",
            )
            .map_err(|e| e.to_string())?;

        let mut csv = String::from("source_text,source_lang,target_lang,summary,note,source_id,saved_at,updated_at\n");
        let rows = stmt
            .query_map([], |row| {
                Ok((
                    row.get::<_, String>(0).unwrap_or_default(),
                    row.get::<_, String>(1).unwrap_or_default(),
                    row.get::<_, String>(2).unwrap_or_default(),
                    row.get::<_, String>(3).unwrap_or_default(),
                    row.get::<_, String>(4).unwrap_or_default(),
                    row.get::<_, String>(5).unwrap_or_default(),
                    row.get::<_, String>(6).unwrap_or_default(),
                    row.get::<_, String>(7).unwrap_or_default(),
                ))
            })
            .map_err(|e| e.to_string())?;

        for r in rows.flatten() {
            let escape = |s: &str| format!("\"{}\"", s.replace('"', "\"\""));
            csv.push_str(&format!(
                "{},{},{},{},{},{},{},{}\n",
                escape(&r.0),
                escape(&r.1),
                escape(&r.2),
                escape(&r.3),
                escape(&r.4),
                escape(&r.5),
                escape(&r.6),
                escape(&r.7)
            ));
        }

        Ok(csv)
    }
}
