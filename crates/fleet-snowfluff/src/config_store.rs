//! Loads and saves the typed app config at the platform config
//! directory derived from the app identifier (app-config spec: "Typed
//! config with validation"). `fleet_snowfluff_core::config` has the
//! pure sanitize/serialize logic and is fully tested against string
//! content; this module is just the thin file-I/O layer that logic was
//! deliberately kept decoupled from.
//!
//! Legacy-config migration (task 5.3's pure logic) isn't wired up here
//! yet -- the app-config spec ties it to also removing the legacy
//! `DesktopPet` autostart registry value and registering the new
//! autostart, so hooking it up before autostart (task group 15) exists
//! would leave that cleanup half-done. Until then, a first run simply
//! starts from `Config::default()`, same as a missing file.

use fleet_snowfluff_core::{config, Config, VoiceLanguage};
use tauri::{AppHandle, Manager};

fn config_path(app: &AppHandle) -> Option<std::path::PathBuf> {
    app.path().app_config_dir().ok().map(|dir| dir.join("config.json"))
}

/// Loads and sanitizes the config file, or `Config::default()` if it's
/// missing, unreadable, or corrupt -- app-config spec's "Corrupt file
/// recovers to defaults" and "missing file yields full defaults".
pub fn load(app: &AppHandle, available_voice_languages: &[VoiceLanguage]) -> Config {
    let Some(path) = config_path(app) else { return Config::default() };
    match std::fs::read_to_string(&path) {
        Ok(contents) => config::load_from_str(&contents, available_voice_languages),
        Err(_) => Config::default(),
    }
}

/// Writes `config` to disk, creating the config directory if needed.
/// Best-effort: a write failure is logged, not propagated, since no
/// caller (a settings-control change) has a sensible way to roll back
/// the in-memory state change that triggered the save.
pub fn save(app: &AppHandle, cfg: &Config) {
    let Some(path) = config_path(app) else {
        log::error!("could not resolve app config directory; settings will not persist");
        return;
    };
    if let Some(dir) = path.parent() {
        if let Err(err) = std::fs::create_dir_all(dir) {
            log::error!("failed to create config dir {dir:?}: {err}");
            return;
        }
    }
    if let Err(err) = std::fs::write(&path, config::to_json_string(cfg)) {
        log::error!("failed to write config to {path:?}: {err}");
    }
}
