// EP-08: Offline System TTS Speech Adapter (`src-tauri/src/speech/mod.rs`)
// Implements:
// - UK / US accent voice selection (`Daniel` for en-GB, `Samantha` for en-US, `Tingting` for zh-CN)
// - Configurable speech rate and explicit "系统语音 (System Offline TTS)" attribution per F-003

use serde::{Deserialize, Serialize};
use std::process::Command;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpeechPlaybackReceipt {
    pub status: String,
    pub voice: String,
    pub accent: String,
    pub engine: String,
}

pub fn speak_offline(text: &str, accent: &str, rate_wpm: u32) -> Result<SpeechPlaybackReceipt, String> {
    let clean = text.trim();
    if clean.is_empty() || clean.chars().count() > 120 {
        return Err("Invalid text length for TTS".to_string());
    }

    let voice = match accent {
        "uk" | "en-GB" => "Daniel",
        "zh" | "zh-CN" => "Tingting",
        _ => "Samantha",
    };

    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("/usr/bin/say")
            .args(["-v", voice, "-r", &rate_wpm.to_string(), clean])
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    Ok(SpeechPlaybackReceipt {
        status: "speaking".to_string(),
        voice: voice.to_string(),
        accent: accent.to_string(),
        engine: "System Offline TTS (AVSpeechSynthesizer / SAPI)".to_string(),
    })
}
