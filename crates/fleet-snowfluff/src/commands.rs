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

/// The short git commit this binary was built from (via shadow-rs,
/// build.rs), shown on the about tab as "Build: {commit}".
#[tauri::command]
pub fn build_commit() -> &'static str { crate::build::SHORT_COMMIT }

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
    /// Absolute path to `config.json`, shown next to the instance-count
    /// control so a user who sets it too high and hits the resulting
    /// crash/lag (task/bug: uncapped instance count can overwhelm the
    /// tick loop) has a concrete path to manually edit back down --
    /// differs by platform (`app_config_dir`), so it can't be a static
    /// string in the locale files.
    config_path: String,
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
        config_path: config_store::config_path(&app)
            .map(|p| p.display().to_string())
            .unwrap_or_default(),
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

/// Toggles the real OS-level login item (task 15.1) and persists the
/// setting. If the OS call fails (e.g. sandboxing denies it on some
/// Linux desktop environments), the config still records the user's
/// intent -- lib.rs's startup reconciliation (comparing the OS's
/// actual state against `config.auto_startup`) will retry it on the
/// next launch.
#[tauri::command]
pub fn set_auto_startup(enabled: bool, app: AppHandle, config: State<Mutex<Config>>) {
    use tauri_plugin_autostart::ManagerExt;
    let autolaunch = app.autolaunch();
    let result = if enabled { autolaunch.enable() } else { autolaunch.disable() };
    if let Err(err) = result {
        log::warn!("failed to {} autostart: {err}", if enabled { "enable" } else { "disable" });
    }
    apply_and_save(&app, &config, |c| c.auto_startup = enabled);
}

/// Persists skip-all-updates (auto-update spec's opt-out).
#[tauri::command]
pub fn set_skip_updates(enabled: bool, app: AppHandle, config: State<Mutex<Config>>) {
    apply_and_save(&app, &config, |c| c.skip_updates = enabled);
}

/// Persists skip-this-version: the startup check (14.2) won't prompt
/// again for this specific version, but manual checks and other
/// versions are unaffected.
#[tauri::command]
pub fn set_skip_version(version: String, app: AppHandle, config: State<Mutex<Config>>) {
    apply_and_save(&app, &config, |c| c.skip_version = Some(version));
}

#[derive(serde::Serialize, Clone)]
pub struct UpdateInfo {
    pub version: String,
    pub body: Option<String>,
}

/// Reads whatever the startup check (updater.rs) already found, if
/// anything, without making another network request. The settings
/// webview calls this once on load to decide whether to default to the
/// update tab and show the result immediately -- previously it instead
/// re-ran `check_for_update` itself whenever opened via the startup
/// path, a redundant second GitHub round-trip that could itself fail
/// (transient network blip, rate limit) independently of the first one
/// having already succeeded.
#[tauri::command]
pub fn pending_update(
    pending: State<Mutex<Option<tauri_plugin_updater::Update>>>,
) -> Option<UpdateInfo> {
    pending
        .lock()
        .unwrap()
        .as_ref()
        .map(|update| UpdateInfo { version: update.version.clone(), body: update.body.clone() })
}

/// Manual "Check for Updates" (always available regardless of
/// skip-all-updates, per the auto-update spec). Stashes the found
/// `Update` in the same state the startup check (updater.rs) uses, so
/// a later `install_update` call -- whichever path found it -- has
/// something to install.
#[tauri::command]
pub async fn check_for_update(
    app: AppHandle,
    pending: State<'_, Mutex<Option<tauri_plugin_updater::Update>>>,
) -> Result<Option<UpdateInfo>, String> {
    let found = crate::updater::check(&app).await?;
    let info = found
        .as_ref()
        .map(|update| UpdateInfo { version: update.version.clone(), body: update.body.clone() });
    *pending.lock().unwrap() = found;
    Ok(info)
}

/// Downloads, verifies (against the embedded minisign pubkey), and
/// installs whatever update `check_for_update` most recently found,
/// then restarts the app. Auto-update spec: "Bad signature rejected" --
/// `download_and_install` verifies before installing and returns an
/// error instead, which propagates here as `Err` without touching the
/// running app.
#[tauri::command]
pub async fn install_update(
    app: AppHandle,
    pending: State<'_, Mutex<Option<tauri_plugin_updater::Update>>>,
) -> Result<(), String> {
    let update = pending.lock().unwrap().take().ok_or("no update available to install")?;
    update.download_and_install(|_, _| {}, || {}).await.map_err(|e| e.to_string())?;
    app.restart();
}
