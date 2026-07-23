//! Loads and saves the typed app config at the platform config
//! directory derived from the app identifier (app-config spec: "Typed
//! config with validation"). `fleet_snowfluff_core::config` has the
//! pure sanitize/serialize logic and is fully tested against string
//! content; this module is just the thin file-I/O layer that logic was
//! deliberately kept decoupled from.

use fleet_snowfluff_core::{config, Config, UiLanguage, VoiceLanguage};
use tauri::{AppHandle, Manager};

pub fn config_path(app: &AppHandle) -> Option<std::path::PathBuf> {
    app.path().app_config_dir().ok().map(|dir| dir.join("config.json"))
}

/// Loads and sanitizes the config file, or attempts a one-shot legacy
/// migration if no Fleet Snowfluff config exists yet but a legacy
/// Ameath one is found (app-config spec's "One-shot migration from
/// Ameath"), or `Config::default()` if neither applies. "Corrupt file
/// recovers to defaults" and "missing file yields full defaults" both
/// fall out of the same match naturally.
pub fn load(
    app: &AppHandle,
    detected_ui_language: UiLanguage,
    available_voice_languages: &[VoiceLanguage],
) -> Config {
    let Some(path) = config_path(app) else { return Config::default() };
    match std::fs::read_to_string(&path) {
        Ok(contents) => config::load_from_str(&contents, available_voice_languages),
        Err(_) => migrate_legacy_if_present(detected_ui_language, available_voice_languages)
            .unwrap_or_default(),
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

/// Looks for `%APPDATA%/ameath_config.json` (legacy's own `CONFIG_FILE`,
/// `constants.py`) and migrates it if present. The `APPDATA` env var
/// check alone makes this naturally a no-op on macOS/Linux without
/// needing an explicit `#[cfg(windows)]` -- legacy only ever ran on
/// Windows, so that variable is never set elsewhere. The legacy file
/// itself is left untouched (app-config spec: "The legacy file SHALL
/// be left unmodified"); only the registry autostart value it wrote is
/// cleaned up, since that's a side effect outside the file itself.
fn migrate_legacy_if_present(
    detected_ui_language: UiLanguage,
    available_voice_languages: &[VoiceLanguage],
) -> Option<Config> {
    let appdata = std::env::var("APPDATA").ok()?;
    let legacy_path = std::path::Path::new(&appdata).join("ameath_config.json");
    let contents = std::fs::read_to_string(&legacy_path).ok()?;
    let legacy_raw: serde_json::Value = match serde_json::from_str(&contents) {
        Ok(value) => value,
        Err(err) => {
            log::warn!(
                "legacy config at {legacy_path:?} is not valid JSON, skipping migration: {err}"
            );
            return None;
        }
    };

    log::info!("migrating legacy config from {legacy_path:?}");
    remove_legacy_autostart_registry_value();
    Some(config::migrate_from_legacy(&legacy_raw, detected_ui_language, available_voice_languages))
}

/// Removes the `DesktopPet` value legacy wrote under
/// `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
/// (`legacy/ameath/config.py`) -- our own autostart registration goes
/// through `tauri-plugin-autostart` instead (task 15.1), so this is
/// purely cleaning up the old entry, not replacing it with a new one
/// (the caller applies the migrated config's `auto_startup` through
/// the normal autostart-sync path afterward, same as any other run).
#[cfg(target_os = "windows")]
fn remove_legacy_autostart_registry_value() {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};

    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let run_key = match hkcu.open_subkey_with_flags(
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        winreg::enums::KEY_SET_VALUE,
    ) {
        Ok(key) => key,
        Err(err) => {
            log::warn!("could not open the Run registry key to remove legacy autostart: {err}");
            return;
        }
    };
    match run_key.delete_value("DesktopPet") {
        Ok(()) => log::info!("removed legacy DesktopPet autostart registry value"),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
        Err(err) => log::warn!("failed to remove legacy DesktopPet registry value: {err}"),
    }
}

#[cfg(not(target_os = "windows"))]
fn remove_legacy_autostart_registry_value() {}
