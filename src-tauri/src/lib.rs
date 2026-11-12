// AI Dictionary — Rust Application Orchestrator (`src-tauri/src/lib.rs`)
// Wires DictionaryService, UserDataRepository, TranslationOrchestrator, Native Selection/OCR/TTS/Config commands,
// and Youdao Dictionary style System Tray / Menu Bar resident lifecycle (Close-to-Tray without quitting).

pub mod config;
pub mod dictionary;
pub mod ocr;
pub mod selection;
pub mod speech;
pub mod translation;
pub mod wordbook;

use dictionary::{DictionaryService, LookupResponse};
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tauri::{Manager, State, WindowEvent};
use translation::{
    build_hymt2_prompt, protect_structured_tokens, restore_and_verify_tokens,
    TranslationOrchestrator, TranslationRequest, PROMPT_TEMPLATE_VERSION,
};
use wordbook::{SavedWord, UserDataRepository};

pub struct AppState {
    pub dict: Arc<DictionaryService>,
    pub user_repo: Arc<UserDataRepository>,
    pub translator: Arc<TranslationOrchestrator>,
    pub native_bridge_bin: PathBuf,
    pub close_to_tray: AtomicBool,
    pub explicit_quit: AtomicBool,
}

/// Intercepts window close requests (`CloseRequested`) on both Windows and macOS:
/// hides the main window to the System Tray / macOS Menu Bar instead of quitting the process,
/// matching Youdao Dictionary's resident background behavior.
pub fn handle_window_close_to_tray<R: tauri::Runtime>(
    window: &tauri::Window<R>,
    event: &WindowEvent,
    state: &AppState,
) {
    if let WindowEvent::CloseRequested { api, .. } = event {
        let should_hide = state.close_to_tray.load(Ordering::SeqCst)
            && !state.explicit_quit.load(Ordering::SeqCst);
        if should_hide {
            api.prevent_close();
            let _ = window.hide();
        }
    }
}

#[tauri::command]
pub fn set_close_to_tray(state: State<'_, AppState>, enabled: bool) -> Result<bool, String> {
    state.close_to_tray.store(enabled, Ordering::SeqCst);
    Ok(state.close_to_tray.load(Ordering::SeqCst))
}

#[tauri::command]
pub fn hide_main_window_to_tray<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<bool, String> {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.hide();
    }
    Ok(true)
}

#[tauri::command]
pub fn restore_main_window_from_tray<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<bool, String> {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
    }
    Ok(true)
}

#[tauri::command]
pub fn lookup_word(
    state: State<'_, AppState>,
    text: String,
    record_history: bool,
) -> Result<LookupResponse, String> {
    let resp = state.dict.lookup_word(&text)?;
    if record_history && resp.found {
        if let Some(entry) = &resp.entry {
            let excerpt = entry
                .senses
                .first()
                .map(|s| format!("{} {}", s.pos, s.zh))
                .unwrap_or_default();
            let _ = state
                .user_repo
                .record_history("lookup", &text, &excerpt, &entry.lang, "zh");
        }
    }
    Ok(resp)
}

#[tauri::command]
pub fn save_word(
    state: State<'_, AppState>,
    entry_id: Option<String>,
    source_text: String,
    source_lang: String,
    target_lang: String,
    summary_snapshot: String,
    source_id: String,
    note: Option<String>,
    tags: Vec<String>,
) -> Result<SavedWord, String> {
    state.user_repo.save_word(
        entry_id.as_deref(),
        &source_text,
        &source_lang,
        &target_lang,
        &summary_snapshot,
        &source_id,
        note.as_deref(),
        &tags,
    )
}

#[tauri::command]
pub fn set_privacy_mode(state: State<'_, AppState>, enabled: bool) -> Result<bool, String> {
    state.user_repo.set_privacy_mode(enabled);
    Ok(state.user_repo.is_privacy_mode())
}

#[tauri::command]
pub fn export_wordbook_csv(state: State<'_, AppState>) -> Result<String, String> {
    state.user_repo.export_wordbook_csv()
}

#[tauri::command]
pub fn cancel_translation(state: State<'_, AppState>, request_id: String) -> Result<bool, String> {
    Ok(state.translator.cancel_request(&request_id))
}

#[tauri::command]
pub fn probe_native_bridge(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    let output = Command::new(&state.native_bridge_bin)
        .output()
        .map_err(|e| format!("Failed to execute native bridge: {}", e))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    serde_json::from_str(&stdout).map_err(|e| format!("Invalid bridge JSON: {}", e))
}
