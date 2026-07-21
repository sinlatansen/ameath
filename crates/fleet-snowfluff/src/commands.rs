//! Tauri commands invoked from the settings webview (task 13.2). Each
//! setter applies the change to the live `PetManager` immediately, then
//! updates the persisted `Config` and writes it to disk -- the
//! settings-ui spec's "Live apply" requirement: every control reflects
//! current state on open and applies to both running pets and config.
//!
//! `Config` (behind its own `Mutex`, alongside `Mutex<PetManager>`) is
//! the single source of truth for round-tripping to disk, since
//! `PetManager` doesn't itself track fields nothing reads yet
//! (`auto_startup`, `skip_updates`, `skip_version` -- task groups 14/15)
//! -- reconstructing `Config` fresh from `PetManager` on every save
//! would silently drop those back to defaults.

use std::sync::Mutex;

use fleet_snowfluff_core::{constants, Config, UiLanguage, VoiceLanguage, WanderStayMode};
use tauri::{AppHandle, State};

use crate::{config_store, manager::PetManager};

/// Returns the active UI language's locale dictionary as raw JSON
/// (task 11.2) for the settings webview to `JSON.parse` and read
/// strings from directly.
#[tauri::command]
pub fn locale_dictionary(state: State<Mutex<PetManager>>) -> String {
    state.lock().unwrap().locale_dictionary_json().to_string()
}

#[derive(serde::Serialize)]
pub struct PersonalizationSnapshot {
    config: Config,
    scale_options: Vec<f64>,
    opacity_options: Vec<f64>,
    monitor_count: usize,
    voice_languages_with_clips: Vec<VoiceLanguage>,
}

#[tauri::command]
pub fn get_personalization(
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) -> PersonalizationSnapshot {
    PersonalizationSnapshot {
        config: config.lock().unwrap().clone(),
        scale_options: constants::scale_options(),
        opacity_options: constants::transparency_options(),
        monitor_count: app.available_monitors().map(|m| m.len()).unwrap_or(1),
        voice_languages_with_clips: manager.lock().unwrap().voice_languages_with_clips().to_vec(),
    }
}

/// Applies `update` to the live manager, mutates the cached `Config`
/// through `set_field`, and persists -- the shared tail every setter
/// command below runs, so each one only has to say what's different.
fn apply_and_save(
    app: &AppHandle,
    config: &State<Mutex<Config>>,
    update: impl FnOnce(&mut Config),
) {
    let mut cfg = config.lock().unwrap();
    update(&mut cfg);
    config_store::save(app, &cfg);
}

#[tauri::command]
pub fn set_scale_index(
    index: usize,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    let options = constants::scale_options();
    let index = index.min(options.len() - 1);
    manager.lock().unwrap().set_scale(options[index]);
    apply_and_save(&app, &config, |c| c.scale_index = index);
}

#[tauri::command]
pub fn set_opacity_index(
    index: usize,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    let options = constants::transparency_options();
    let index = index.min(options.len() - 1);
    manager.lock().unwrap().set_opacity(options[index] as f32);
    apply_and_save(&app, &config, |c| c.transparency_index = index);
}

#[tauri::command]
pub fn set_display_priority(
    mode: i64,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_display_priority(mode);
    apply_and_save(&app, &config, |c| c.display_priority = mode);
}

#[tauri::command]
pub fn set_wander_stay_mode(
    mode: i64,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().settings.wander_idle_stay_mode =
        WanderStayMode::from_legacy_mode(mode as i32);
    apply_and_save(&app, &config, |c| c.wander_idle_stay_mode = mode);
}

#[tauri::command]
pub fn set_total_screen(
    enabled: bool,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_total_screen(enabled);
    apply_and_save(&app, &config, |c| c.total_screen = enabled);
}

#[tauri::command]
pub fn set_monitor_index(
    index: i64,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_monitor_index(index);
    apply_and_save(&app, &config, |c| c.screen_index = index);
}

#[tauri::command]
pub fn set_window_snap(
    enabled: bool,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_window_snap(enabled);
    apply_and_save(&app, &config, |c| c.window_snap = enabled);
}

#[tauri::command]
pub fn set_instance_count(
    count: usize,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_instance_count(count);
    apply_and_save(&app, &config, |c| c.instance_count = count);
}

#[tauri::command]
pub fn set_ui_language(
    language: UiLanguage,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_ui_language(language);
    apply_and_save(&app, &config, |c| c.ui_language = language);
    // The webview re-renders its own content on a language change, but
    // the native title bar is Rust-owned and needs updating separately.
    let title = fleet_snowfluff_core::dictionary(language)
        .get("settings.window_title")
        .cloned()
        .unwrap_or_default();
    crate::settings_window::refresh_title(&app, &title);
}

#[tauri::command]
pub fn set_voice_enabled(
    enabled: bool,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_voice_enabled(enabled);
    apply_and_save(&app, &config, |c| c.voice_enabled = enabled);
}

#[tauri::command]
pub fn set_voice_volume(
    percent: i64,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_voice_volume_percent(percent);
    apply_and_save(&app, &config, |c| c.voice_volume = percent);
}

#[tauri::command]
pub fn set_voice_language(
    language: VoiceLanguage,
    app: AppHandle,
    manager: State<Mutex<PetManager>>,
    config: State<Mutex<Config>>,
) {
    manager.lock().unwrap().set_voice_language(language);
    apply_and_save(&app, &config, |c| c.voice_language = language);
}

/// Persists the autostart toggle only -- the actual OS-level
/// registration (`tauri-plugin-autostart`) lands with task group 15;
/// until then this just remembers the user's intent so 15's wiring has
/// a value to apply on startup once it exists.
#[tauri::command]
pub fn set_auto_startup(enabled: bool, app: AppHandle, config: State<Mutex<Config>>) {
    apply_and_save(&app, &config, |c| c.auto_startup = enabled);
}

/// Persists skip-all-updates (auto-update spec's opt-out). The rest of
/// the update tab (manual check, current/latest version, install,
/// skip-this-version) needs `tauri-plugin-updater` wired up, which is
/// task group 14 -- this one control doesn't depend on it.
#[tauri::command]
pub fn set_skip_updates(enabled: bool, app: AppHandle, config: State<Mutex<Config>>) {
    apply_and_save(&app, &config, |c| c.skip_updates = enabled);
}
