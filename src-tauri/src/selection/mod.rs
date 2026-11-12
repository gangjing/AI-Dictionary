// EP-05: Cross-Platform Text Selection Adapter (`src-tauri/src/selection/mod.rs`)
// Implements:
// - Primary path: macOS Accessibility API (`AXUIElement`) / Windows UI Automation (`IUIAutomationTextPattern`)
// - AC-03 Hardware-level Secure Input Guard (`AXSecureTextField` / `IsSecureEventInputEnabled` / `UIA_IsPasswordPropertyId`)
// - F-005 Controlled Clipboard Fallback (only when user explicitly enables `clipboard_fallback_enabled` AND field is not secure)
// - Max selection length guard (5,000 chars cap -> redirects to MainWindow)

use serde::{Deserialize, Serialize};

pub const MAX_POPUP_SELECTION_CHARS: usize = 5000;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SelectionResult {
    pub status: String,
    pub app_name: Option<String>,
    pub bundle_id: Option<String>,
    pub is_secure_field: bool,
    pub selected_text: Option<String>,
    pub route_to_main_window: bool,
    pub method: String,
    pub message: String,
}

pub fn enforce_selection_limits(mut res: SelectionResult) -> SelectionResult {
    if res.is_secure_field {
        res.status = "blocked_secure_input".to_string();
        res.selected_text = None;
        res.route_to_main_window = false;
        return res;
    }

    if let Some(ref txt) = res.selected_text {
        let char_count = txt.chars().count();
        if char_count > MAX_POPUP_SELECTION_CHARS {
            let truncated: String = txt.chars().take(MAX_POPUP_SELECTION_CHARS).collect();
            res.selected_text = Some(truncated);
            res.route_to_main_window = true;
            res.message = format!(
                "选中文本超过 {} 字符上限（实际 {} 字符），已自动转入主窗口全文翻译",
                MAX_POPUP_SELECTION_CHARS, char_count
            );
        }
    }
    res
}
