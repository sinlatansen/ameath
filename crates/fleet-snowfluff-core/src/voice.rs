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

/// Picks which clip (by index into the active pack) plays next, avoiding
/// a fourth consecutive play of the same clip (legacy allows up to three
/// in a row) -- ported from legacy's `play_random_voice` anti-repeat
/// rule. Actual playback (rodio) is a shell concern; this only decides
/// *which* clip.
#[derive(Debug, Clone, Default)]
pub struct ClipSelector {
    last_index: Option<usize>,
    consecutive_count: u32,
}

impl ClipSelector {
    pub fn new() -> Self { Self::default() }

    /// Picks an index in `0..clip_count`. Panics if `clip_count == 0` --
    /// callers should not invoke this on an empty pack (the
    /// `resolve_voice_language`/manifest invariant already guarantees a
    /// selected pack is non-empty).
    pub fn pick(&mut self, clip_count: usize, rng: &mut impl rand::Rng) -> usize {
        assert!(clip_count > 0, "ClipSelector::pick called with an empty pack");

        let index = if clip_count == 1 {
            0
        } else if self.consecutive_count >= 2 {
            let last = self.last_index.expect("consecutive_count > 0 implies a last_index");
            loop {
                let candidate = rng.random_range(0..clip_count);
                if candidate != last {
                    break candidate;
                }
            }
        } else {
            rng.random_range(0..clip_count)
        };

        if Some(index) == self.last_index {
            self.consecutive_count += 1;
        } else {
            self.last_index = Some(index);
            self.consecutive_count = 0;
        }
        index
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

    fn rng() -> rand::rngs::StdRng {
        use rand::SeedableRng;
        rand::rngs::StdRng::seed_from_u64(11)
    }

    #[test]
    fn single_clip_always_picks_index_zero() {
        let mut selector = ClipSelector::new();
        let mut rng = rng();
        for _ in 0..10 {
            assert_eq!(selector.pick(1, &mut rng), 0);
        }
    }

    #[test]
    fn never_plays_the_same_clip_four_times_in_a_row() {
        // Legacy's own comment is explicit: "避免连续播放同一语音超过三次"
        // -- avoid playing the same voice consecutively *more than three*
        // times. Up to 3 in a row is allowed; the guard only blocks the 4th.
        let mut selector = ClipSelector::new();
        let mut rng = rng();
        let mut history = Vec::new();
        for _ in 0..500 {
            history.push(selector.pick(5, &mut rng));
        }
        for window in history.windows(4) {
            assert!(
                !(window[0] == window[1] && window[1] == window[2] && window[2] == window[3]),
                "clip {} played four times in a row",
                window[0]
            );
        }
    }

    #[test]
    fn two_clips_never_reach_a_fourth_consecutive_play() {
        let mut selector = ClipSelector::new();
        let mut rng = rng();
        let mut history = Vec::new();
        for _ in 0..50 {
            history.push(selector.pick(2, &mut rng));
        }
        for window in history.windows(4) {
            assert!(!(window[0] == window[1] && window[1] == window[2] && window[2] == window[3]));
        }
    }
}
