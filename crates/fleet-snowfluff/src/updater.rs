//! GitHub Releases-backed auto-update (task group 14). `tauri-plugin-
//! updater` does the download/verify/install work (signed against the
//! embedded minisign pubkey in tauri.conf.json -- see design.md D10);
//! this module is the startup-check policy (skip-all / skip-version)
//! and the glue that hands a found `Update` to the settings webview.

use std::sync::Mutex;

use fleet_snowfluff_core::Config;
use tauri::{AppHandle, Manager};
use tauri_plugin_updater::{Update, UpdaterExt};

pub async fn check(app: &AppHandle) -> Result<Option<Update>, String> {
    let updater = app.updater().map_err(|e| e.to_string())?;
    updater.check().await.map_err(|e| e.to_string())
}

/// Background startup check (14.2): unless skip-all-updates is set,
/// checks once at launch; if a newer version is found and it isn't the
/// one the user previously chose to skip, stashes it (for the settings
/// webview's install button, via `check_for_update`/`install_update` in
/// commands.rs sharing the same `Mutex<Option<Update>>` state) and
/// opens settings straight to the update tab.
pub fn spawn_startup_check(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let skip_all = app.state::<Mutex<Config>>().lock().unwrap().skip_updates;
        if skip_all {
            return;
        }

        let update = match check(&app).await {
            Ok(Some(update)) => update,
            Ok(None) => return,
            Err(err) => {
                log::warn!("startup update check failed: {err}");
                return;
            }
        };

        let already_skipped = {
            let config = app.state::<Mutex<Config>>();
            let guard = config.lock().unwrap();
            guard.skip_version.as_deref() == Some(update.version.as_str())
        };
        if already_skipped {
            return;
        }

        log::info!("update available: {}", update.version);
        *app.state::<Mutex<Option<Update>>>().lock().unwrap() = Some(update);

        let title = {
            let manager = app.state::<Mutex<crate::manager::PetManager>>();
            let m = manager.lock().unwrap();
            fleet_snowfluff_core::dictionary(m.ui_language())
                .get("settings.window_title")
                .cloned()
                .unwrap_or_default()
        };
        crate::settings_window::open_or_focus_settings(&app, &title, Some("update"));
    });
}
