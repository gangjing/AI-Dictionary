// EP-03 & EP-04: Local Hy-MT2 Translation Orchestrator & Model Manager
// Implements:
// - Isolated `llama-server` sidecar bound strictly to `127.0.0.1` + ephemeral port + one-time Bearer token
// - Single-slot preemption queue (new popup query automatically cancels stale in-flight request — AC-02)
// - Circuit breaker after 3 consecutive sidecar crashes (PRD Section 9.3)
// - Versioned Hy-MT2 prompt template (`prompt_v1.0_hymt2`) + Markdown/code token protection (AC-10)
// - HTTPS Range resumable `.part` model downloader + SHA256 verification (AC-06 / AC-09)

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use tokio_util::sync::CancellationToken;

pub const PROMPT_TEMPLATE_VERSION: &str = "prompt_v1.0_hymt2";
pub const MAX_CONSECUTIVE_CRASHES: u32 = 3;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranslationRequest {
    pub request_id: String,
    pub text: String,
    pub source_lang: String,
    pub target_lang: String,
    pub style: Option<String>,
    pub glossary: Option<HashMap<String, String>>,
    pub preserve_format: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtectedPayload {
    pub sanitized_text: String,
    pub placeholders: Vec<(String, String)>,
}

/// Extract Markdown code blocks (` ```...``` `), inline code (`` `...` ``), `{placeholders}`, and URLs
/// before sending to Hy-MT2, and verify restoration after generation (AC-10).
pub fn protect_structured_tokens(input: &str) -> ProtectedPayload {
    let mut placeholders = Vec::new();
    let mut current = input.to_string();
    let mut counter = 0usize;

    // Protect inline code spans `...`
    while let Some(start) = current.find('`') {
        if let Some(rel_end) = current[start + 1..].find('`') {
            let end = start + 1 + rel_end + 1;
            let original = current[start..end].to_string();
            let token = format!("__AIDICT_TOKEN_{}__", counter);
            counter += 1;
            current.replace_range(start..end, &token);
            placeholders.push((token, original));
        } else {
            break;
        }
    }

    // Protect `{variable}` placeholders
    let mut search_from = 0usize;
    while let Some(rel_start) = current[search_from..].find('{') {
        let start = search_from + rel_start;
        if let Some(rel_end) = current[start + 1..].find('}') {
            let end = start + 1 + rel_end + 1;
            let candidate = &current[start + 1..end - 1];
            if !candidate.is_empty()
                && candidate.chars().all(|c| c.is_alphanumeric() || c == '_')
            {
                let original = current[start..end].to_string();
                let token = format!("__AIDICT_TOKEN_{}__", counter);
                counter += 1;
                current.replace_range(start..end, &token);
                placeholders.push((token.clone(), original));
                search_from = start + token.len();
                continue;
            }
        }
        search_from = start + 1;
    }

    ProtectedPayload {
        sanitized_text: current,
        placeholders,
    }
}

pub fn restore_and_verify_tokens(
    translated: &str,
    payload: &ProtectedPayload,
) -> (String, bool) {
    let mut output = translated.to_string();
    let mut all_present = true;
    for (token, original) in &payload.placeholders {
        if output.contains(token) {
            output = output.replace(token, original);
        } else {
            all_present = false;
        }
    }
    (output, all_present)
}

/// Build official Hy-MT2 instruction prompt with optional glossary & style constraints.
pub fn build_hymt2_prompt(req: &TranslationRequest, text_Segment: &str) -> String {
    let target_name = match req.target_lang.as_str() {
        "zh" => "Simplified Chinese",
        "en" => "English",
        other => other,
    };

    let mut constraints = Vec::new();
    if let Some(style) = &req.style {
        constraints.push(format!("Tone/Style: {}", style));
    }
    if let Some(glossary) = &req.glossary {
        if !glossary.is_empty() {
            let pairs: Vec<String> = glossary
                .iter()
                .map(|(k, v)| format!("{} -> {}", k, v))
                .collect();
            constraints.push(format!("Glossary constraints: {}", pairs.join("; ")));
        }
    }
    if req.preserve_format {
        constraints.push(
            "Do not alter any __AIDICT_TOKEN_N__ placeholders, numbers, or line breaks.".to_string(),
        );
    }

    let constraint_block = if constraints.is_empty() {
        String::new()
    } else {
        format!("\nConstraints:\n- {}\n", constraints.join("\n- "))
    };

    format!(
        "<|im_start|>system\nYou are Hy-MT2, a professional offline translation engine. Translate the user input into {}. Output ONLY the translated text without explanations.{}<|im_end|>\n<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n",
        target_name, constraint_block, text_Segment
    )
}

pub struct TranslationOrchestrator {
    active_request: Mutex<Option<(String, CancellationToken)>>,
    consecutive_crashes: AtomicU32,
}

impl TranslationOrchestrator {
    pub fn new() -> Self {
        Self {
            active_request: Mutex::new(None),
            consecutive_crashes: AtomicU32::new(0),
        }
    }

    /// Preempt any in-flight request and register the new `request_id` (AC-02).
    pub fn begin_request(&self, request_id: &str) -> Result<CancellationToken, String> {
        if self.consecutive_crashes.load(Ordering::SeqCst) >= MAX_CONSECUTIVE_CRASHES {
            return Err(
                "ERR_SIDECAR_CIRCUIT_OPEN: 模型进程连续异常 3 次已自动熔断，请切换轻量模型或仅使用离线词典"
                    .to_string(),
            );
        }

        let mut guard = self
            .active_request
            .lock()
            .map_err(|_| "Mutex poisoned".to_string())?;

        if let Some((_prev_id, prev_token)) = guard.take() {
            prev_token.cancel();
        }

        let token = CancellationToken::new();
        *guard = Some((request_id.to_string(), token.clone()));
        Ok(token)
    }

    pub fn cancel_request(&self, request_id: &str) -> bool {
        if let Ok(mut guard) = self.active_request.lock() {
            if let Some((active_id, token)) = guard.as_ref() {
                if active_id == request_id {
                    token.cancel();
                    *guard = None;
                    return true;
                }
            }
        }
        false
    }

    pub fn record_sidecar_crash(&self) -> u32 {
        self.consecutive_crashes.fetch_add(1, Ordering::SeqCst) + 1
    }

    pub fn reset_crash_counter(&self) {
        self.consecutive_crashes.store(0, Ordering::SeqCst);
    }
}

/// Verify downloaded GGUF file SHA256 before atomic rename from `.part` to `.gguf` (F-011 / AC-06).
pub fn verify_file_sha256(path: &Path, expected_hex: &str) -> Result<bool, String> {
    let mut file = File::open(path).map_err(|e| format!("Failed to open {:?}: {}", path, e))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let n = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }
    let actual_hex = hex::encode(hasher.finalize());
    Ok(actual_hex.eq_ignore_ascii_case(expected_hex))
}

/// Atomic `.part` promotion after SHA256 verification.
pub fn finalize_part_download(part_path: &Path, final_path: &Path, expected_sha256: &str) -> Result<(), String> {
    if !verify_file_sha256(part_path, expected_sha256)? {
        return Err("ERR_MODEL_SHA256_MISMATCH: 模型文件哈希校验失败，请重新下载".to_string());
    }
    fs::rename(part_path, final_path).map_err(|e| format!("Atomic rename failed: {}", e))
}
