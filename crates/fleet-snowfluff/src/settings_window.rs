//! Opens (or focuses) the settings webview window (task 12.1/12.3):
//! shared by the tray's Settings item and the quick menu's, since the
//! settings-ui spec requires only one instance to ever exist regardless
//! of which entry point was used. The window's tabs (personalization /
//! update / about) land in task group 13 -- for now it loads whatever
//! `ui/dist` currently serves.

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

const SETTINGS_WINDOW_LABEL: &str = "settings";

pub fn open_or_focus_settings(app: &AppHandle, title: &str) {
    if let Some(window) = app.get_webview_window(SETTINGS_WINDOW_LABEL) {
        window.show().ok();
        window.set_focus().ok();
        return;
    }

    let result =
        WebviewWindowBuilder::new(app, SETTINGS_WINDOW_LABEL, WebviewUrl::App("index.html".into()))
            .title(title)
            .inner_size(480.0, 560.0)
            .resizable(true)
            .center()
            .build();

    if let Err(err) = result {
        log::error!("failed to open settings window: {err}");
    }
}
