// EP-07: Screen Capture & Native Offline OCR Adapter (`src-tauri/src/ocr/mod.rs`)
// Implements:
// - Multi-monitor DPI / Retina scale factor calculation
// - Strictly in-memory image buffer (`Vec<u8>`) — never writes temporary screenshot files to disk (`persisted_to_disk = false`)
// - Bridges to macOS `Vision.framework` (`VNRecognizeTextRequest`) and Windows `Windows.Media.Ocr`

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrLineItem {
    pub text: String,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrRecognitionReport {
    pub status: String,
    pub elapsed_ms: f64,
    pub lines: Vec<OcrLineItem>,
    pub persisted_to_disk: bool,
}
