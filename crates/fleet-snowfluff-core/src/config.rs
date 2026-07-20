//! Typed, validated app config (design.md D9), ported from
//! `legacy/ameath/config.py`'s `DEFAULT_CONFIG` / `_sanitize_config`.
//! Every field except `music_enabled`/`music_volume` (dropped — the
//! music player is out of scope) carries over unchanged; `ui_language`
//! and `voice_language` are new.
//!
//! Sanitization takes a loosely-typed `serde_json::Value` rather than
//! deserializing straight into `Config`, so malformed or out-of-range
//! input degrades gracefully field-by-field (matching legacy) instead of
//! failing the whole parse. Actual file I/O and path resolution
//! (`%APPDATA%/ameath_config.json`, the new `app_config_dir/config.json`)
//! are the shell's job; this module works over string contents so it's
//! testable without a filesystem.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    constants::{
        DEFAULT_SCALE_INDEX, DEFAULT_SCREEN_INDEX, DEFAULT_TRANSPARENCY_INDEX,
        DEFAULT_VOICE_ENABLED, DEFAULT_VOICE_VOLUME, DEFAULT_WANDER_IDLE_STAY_MODE,
    },
    locale::UiLanguage,
    voice::{resolve_voice_language, VoiceLanguage},
};

const SCALE_OPTIONS_LEN: usize = 20;
const TRANSPARENCY_OPTIONS_LEN: usize = 10;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Config {
    pub total_screen: bool,
    pub screen_index: i64,
    pub scale_index: usize,
    pub window_snap: bool,
    pub transparency_index: usize,
    pub auto_startup: bool,
    pub click_through: bool,
    pub follow_mouse: bool,
    pub display_priority: i64,
    pub wander_idle_stay_mode: i64,
    pub instance_count: usize,
    pub skip_updates: bool,
    pub skip_version: Option<String>,
    pub voice_enabled: bool,
    pub voice_volume: i64,
    pub ui_language: UiLanguage,
    pub voice_language: VoiceLanguage,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            total_screen: true,
            screen_index: DEFAULT_SCREEN_INDEX as i64,
            scale_index: DEFAULT_SCALE_INDEX,
            window_snap: true,
            transparency_index: DEFAULT_TRANSPARENCY_INDEX,
            auto_startup: true,
            click_through: false,
            follow_mouse: false,
            display_priority: 1,
            wander_idle_stay_mode: DEFAULT_WANDER_IDLE_STAY_MODE as i64,
            instance_count: 1,
            skip_updates: false,
            skip_version: None,
            voice_enabled: DEFAULT_VOICE_ENABLED,
            voice_volume: DEFAULT_VOICE_VOLUME as i64,
            ui_language: UiLanguage::default(),
            voice_language: VoiceLanguage::default(),
        }
    }
}

fn coerce_bool(v: Option<&Value>, default: bool) -> bool {
    match v {
        Some(Value::Bool(b)) => *b,
        _ => default,
    }
}

/// Out-of-range values fall back to `default` rather than clamping,
/// matching legacy's `_coerce_int`.
fn coerce_i64_ranged(v: Option<&Value>, default: i64, min: i64, max: i64) -> i64 {
    match v.and_then(Value::as_i64) {
        Some(n) if n >= min && n <= max => n,
        _ => default,
    }
}

fn coerce_i64_min(v: Option<&Value>, default: i64, min: i64) -> i64 {
    match v.and_then(Value::as_i64) {
        Some(n) if n >= min => n,
        _ => default,
    }
}

fn coerce_usize(v: Option<&Value>, default: usize, min: usize, max: usize) -> usize {
    match v.and_then(Value::as_i64) {
        Some(n) if n >= 0 && (n as usize) >= min && (n as usize) <= max => n as usize,
        _ => default,
    }
}

fn coerce_enum<T: for<'de> Deserialize<'de> + Default>(v: Option<&Value>) -> T {
    v.and_then(|v| serde_json::from_value::<T>(v.clone()).ok()).unwrap_or_default()
}

/// Sanitizes a raw config JSON value into a fully-valid `Config`.
/// `available_voice_languages` is the set of voice packs that actually
/// have clips right now (always includes at least `Zh`); an invalid or
/// empty-pack `voice_language` snaps back to `Zh`.
pub fn sanitize(raw: &Value, available_voice_languages: &[VoiceLanguage]) -> Config {
    let obj = raw.as_object();
    let get = |key: &str| obj.and_then(|o| o.get(key));

    let requested_voice_language: VoiceLanguage = coerce_enum(get("voice_language"));

    Config {
        total_screen: coerce_bool(get("total_screen"), true),
        screen_index: coerce_i64_min(get("screen_index"), DEFAULT_SCREEN_INDEX as i64, 0),
        scale_index: coerce_usize(
            get("scale_index"),
            DEFAULT_SCALE_INDEX,
            0,
            SCALE_OPTIONS_LEN - 1,
        ),
        window_snap: coerce_bool(get("window_snap"), true),
        transparency_index: coerce_usize(
            get("transparency_index"),
            DEFAULT_TRANSPARENCY_INDEX,
            0,
            TRANSPARENCY_OPTIONS_LEN - 1,
        ),
        auto_startup: coerce_bool(get("auto_startup"), true),
        click_through: coerce_bool(get("click_through"), false),
        follow_mouse: coerce_bool(get("follow_mouse"), false),
        display_priority: coerce_i64_ranged(get("display_priority"), 1, 1, 3),
        wander_idle_stay_mode: coerce_i64_ranged(
            get("wander_idle_stay_mode"),
            DEFAULT_WANDER_IDLE_STAY_MODE as i64,
            0,
            2,
        ),
        instance_count: coerce_usize(get("instance_count"), 1, 1, 80),
        skip_updates: coerce_bool(get("skip_updates"), false),
        skip_version: get("skip_version").and_then(Value::as_str).map(str::to_string),
        voice_enabled: coerce_bool(get("voice_enabled"), DEFAULT_VOICE_ENABLED),
        voice_volume: coerce_i64_ranged(get("voice_volume"), DEFAULT_VOICE_VOLUME as i64, 0, 150),
        ui_language: coerce_enum(get("ui_language")),
        voice_language: resolve_voice_language(requested_voice_language, available_voice_languages),
    }
}

/// Loads config from raw file contents. Missing/unreadable/corrupt
/// content yields full defaults, matching legacy's `load_config`.
pub fn load_from_str(contents: &str, available_voice_languages: &[VoiceLanguage]) -> Config {
    match serde_json::from_str::<Value>(contents) {
        Ok(value) => sanitize(&value, available_voice_languages),
        Err(_) => Config {
            voice_language: resolve_voice_language(
                VoiceLanguage::default(),
                available_voice_languages,
            ),
            ..Config::default()
        },
    }
}

/// One-shot migration from the legacy Ameath config (design.md D9):
/// every overlapping field is sanitized the same way as a fresh load
/// (so out-of-range legacy values still get cleaned up), `music_*` keys
/// have no field to land in and are silently dropped, and the two new
/// fields are set from the caller-supplied detection rather than from
/// the (nonexistent, in legacy) source keys.
pub fn migrate_from_legacy(
    legacy_raw: &Value,
    detected_ui_language: UiLanguage,
    available_voice_languages: &[VoiceLanguage],
) -> Config {
    let mut config = sanitize(legacy_raw, available_voice_languages);
    config.ui_language = detected_ui_language;
    config.voice_language =
        resolve_voice_language(VoiceLanguage::default(), available_voice_languages);
    config
}

pub fn to_json_string(config: &Config) -> String {
    serde_json::to_string_pretty(config).expect("Config serialization is infallible")
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn all_voice_languages() -> Vec<VoiceLanguage> { VoiceLanguage::ALL.to_vec() }

    #[test]
    fn defaults_match_legacy_default_config() {
        let config = Config::default();
        assert!(config.total_screen);
        assert_eq!(config.screen_index, 0);
        assert_eq!(config.scale_index, DEFAULT_SCALE_INDEX);
        assert!(config.window_snap);
        assert_eq!(config.transparency_index, DEFAULT_TRANSPARENCY_INDEX);
        assert!(config.auto_startup);
        assert!(!config.click_through);
        assert!(!config.follow_mouse);
        assert_eq!(config.display_priority, 1);
        assert_eq!(config.wander_idle_stay_mode, 2);
        assert_eq!(config.instance_count, 1);
        assert!(!config.skip_updates);
        assert_eq!(config.skip_version, None);
        assert!(config.voice_enabled);
        assert_eq!(config.voice_volume, 100);
    }

    #[test]
    fn corrupt_json_yields_defaults() {
        let config = load_from_str("{not valid json", &all_voice_languages());
        assert_eq!(config, Config { voice_language: VoiceLanguage::Zh, ..Config::default() });
    }

    #[test]
    fn missing_file_content_yields_defaults() {
        let config = load_from_str("", &all_voice_languages());
        assert_eq!(config.instance_count, 1);
    }

    #[test]
    fn partial_config_fills_missing_fields_with_defaults() {
        let raw = json!({ "click_through": true });
        let config = sanitize(&raw, &all_voice_languages());
        assert!(config.click_through);
        assert_eq!(config.scale_index, DEFAULT_SCALE_INDEX);
    }

    #[test]
    fn out_of_range_values_fall_back_to_default_not_clamped() {
        let raw = json!({ "instance_count": 999, "display_priority": 7, "voice_volume": -5 });
        let config = sanitize(&raw, &all_voice_languages());
        assert_eq!(config.instance_count, 1);
        assert_eq!(config.display_priority, 1);
        assert_eq!(config.voice_volume, 100);
    }

    #[test]
    fn wrong_type_values_fall_back_to_default() {
        let raw = json!({ "click_through": "yes", "scale_index": "nine" });
        let config = sanitize(&raw, &all_voice_languages());
        assert!(!config.click_through);
        assert_eq!(config.scale_index, DEFAULT_SCALE_INDEX);
    }

    #[test]
    fn negative_instance_count_falls_back_to_default() {
        let raw = json!({ "instance_count": -3 });
        let config = sanitize(&raw, &all_voice_languages());
        assert_eq!(config.instance_count, 1);
    }

    #[test]
    fn voice_language_snaps_back_when_pack_is_empty() {
        let raw = json!({ "voice_language": "ko" });
        let config = sanitize(&raw, &[VoiceLanguage::Zh]);
        assert_eq!(config.voice_language, VoiceLanguage::Zh);
    }

    #[test]
    fn voice_language_kept_when_pack_has_clips() {
        let raw = json!({ "voice_language": "ja" });
        let config = sanitize(&raw, &[VoiceLanguage::Zh, VoiceLanguage::Ja]);
        assert_eq!(config.voice_language, VoiceLanguage::Ja);
    }

    #[test]
    fn migration_drops_music_keys_and_adds_language_fields() {
        let legacy = json!({
            "total_screen": false,
            "scale_index": 5,
            "click_through": true,
            "instance_count": 3,
            "music_enabled": true,
            "music_volume": 80,
        });
        let config = migrate_from_legacy(&legacy, UiLanguage::Ja, &all_voice_languages());
        assert!(!config.total_screen);
        assert_eq!(config.scale_index, 5);
        assert!(config.click_through);
        assert_eq!(config.instance_count, 3);
        assert_eq!(config.ui_language, UiLanguage::Ja);
        assert_eq!(config.voice_language, VoiceLanguage::Zh);
    }

    #[test]
    fn migration_sanitizes_carried_over_fields_too() {
        let legacy = json!({ "instance_count": 999 });
        let config = migrate_from_legacy(&legacy, UiLanguage::En, &all_voice_languages());
        assert_eq!(config.instance_count, 1);
    }

    #[test]
    fn round_trips_through_json() {
        let config = Config { instance_count: 12, ..Config::default() };
        let json_str = to_json_string(&config);
        let value: Value = serde_json::from_str(&json_str).unwrap();
        let reloaded = sanitize(&value, &all_voice_languages());
        assert_eq!(reloaded, config);
    }
}
