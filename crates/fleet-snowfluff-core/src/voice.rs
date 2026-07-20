//! Voice-language selection and manifest schema (design.md D7). Which
//! languages actually have recorded clips is a runtime fact (only `zh`
//! ships initially) supplied by the caller — loading the manifest files
//! themselves is a shell concern (task 10.2); this module only defines
//! the manifest's shape and the pure snap-back rule that keeps
//! `voice_language` always pointing at a non-empty pack.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum VoiceLanguage {
    #[default]
    Zh,
    Ja,
    En,
    Ko,
}

impl VoiceLanguage {
    pub const ALL: [VoiceLanguage; 4] =
        [VoiceLanguage::Zh, VoiceLanguage::Ja, VoiceLanguage::En, VoiceLanguage::Ko];

    /// The folder name under `assets/voice/` for this language.
    pub fn asset_dir_name(&self) -> &'static str {
        match self {
            VoiceLanguage::Zh => "zh",
            VoiceLanguage::Ja => "ja",
            VoiceLanguage::En => "en",
            VoiceLanguage::Ko => "ko",
        }
    }
}

/// The `manifest.json` schema under each `assets/voice/<lang>/`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VoiceManifest {
    pub language: VoiceLanguage,
    pub clips: Vec<String>,
}

impl VoiceManifest {
    pub fn has_clips(&self) -> bool { !self.clips.is_empty() }
}

/// Ensures `requested` points at a language that actually has clips,
/// falling back to `zh` (which always ships with assets) otherwise.
/// This is the invariant the settings picker's disabled-when-empty UI
/// and config load both rely on: a selected voice language always has
/// assets.
pub fn resolve_voice_language(
    requested: VoiceLanguage,
    languages_with_clips: &[VoiceLanguage],
) -> VoiceLanguage {
    if languages_with_clips.contains(&requested) {
        requested
    } else {
        VoiceLanguage::Zh
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requested_language_kept_when_it_has_clips() {
        let available = [VoiceLanguage::Zh, VoiceLanguage::Ja];
        assert_eq!(resolve_voice_language(VoiceLanguage::Ja, &available), VoiceLanguage::Ja);
    }

    #[test]
    fn empty_language_snaps_back_to_zh() {
        let available = [VoiceLanguage::Zh];
        assert_eq!(resolve_voice_language(VoiceLanguage::Ko, &available), VoiceLanguage::Zh);
    }

    #[test]
    fn manifest_reports_has_clips_correctly() {
        let empty = VoiceManifest { language: VoiceLanguage::En, clips: vec![] };
        let full = VoiceManifest { language: VoiceLanguage::Zh, clips: vec!["a.wav".into()] };
        assert!(!empty.has_clips());
        assert!(full.has_clips());
    }

    #[test]
    fn manifest_deserializes_from_the_shipped_schema() {
        let json = r#"{"language":"zh","clips":["a.wav","b.wav"]}"#;
        let manifest: VoiceManifest = serde_json::from_str(json).unwrap();
        assert_eq!(manifest.language, VoiceLanguage::Zh);
        assert_eq!(manifest.clips.len(), 2);
    }
}
