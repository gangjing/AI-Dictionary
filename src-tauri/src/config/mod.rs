// EP-12: System Configuration, Hotkey Conflict Guard & Privacy Sovereignty (`src-tauri/src/config/mod.rs`)
// Implements F-012:
// - Global shortcut conflict validation
// - Idle model unload timer settings
// - Clipboard fallback & selection icon opt-in switches

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub hotkey_lookup_mac: String,
    pub hotkey_lookup_win: String,
    pub hotkey_ocr_mac: String,
    pub hotkey_ocr_win: String,
    pub hotkey_main_mac: String,
    pub hotkey_main_win: String,
    pub selection_icon_enabled: bool,
    pub clipboard_fallback_enabled: bool,
    pub context_enhanced_lookup: bool,
    pub auto_start: bool,
    pub idle_unload_minutes: u32,
    pub default_target_lang: String,
    pub tts_rate: f32,
    pub onboarding_completed: bool,
    pub custom_glossary: HashMap<String, String>,
}

const RESERVED_OS_SHORTCUTS: &[&str] = &[
    "Command+C",
    "Command+V",
    "Command+Q",
    "Command+Space",
    "Ctrl+C",
    "Ctrl+V",
    "Alt+F4",
];

pub fn validate_hotkey(shortcut: &str) -> Result<(), String> {
    let trimmed = shortcut.trim();
    if RESERVED_OS_SHORTCUTS
        .iter()
        .any(|s| s.eq_ignore_ascii_case(trimmed))
    {
        return Err(format!(
            "ERR_HOTKEY_CONFLICT: 快捷键 '{}' 与系统核心保留热键冲突，请更换组合键",
            trimmed
        ));
    }
    Ok(())
}
