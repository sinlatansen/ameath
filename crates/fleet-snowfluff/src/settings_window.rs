//! Opens (or focuses) the settings webview window (task 12.1/12.3):
//! shared by the tray's Settings item, the quick menu's, and the
//! auto-update startup check (14.2), since the settings-ui spec
//! requires only one instance to ever exist regardless of entry point.

use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

const SETTINGS_WINDOW_LABEL: &str = "settings";

/// Opens the settings window, or focuses it if already open.
/// `initial_tab` selects which tab should be active -- `None` leaves it
/// at whatever the window (new or already-open) currently defaults to;
/// `Some("update")` is how the startup update check (14.2) jumps
/// straight to the update tab. A fresh window gets it via a URL query
/// param (read once at load); an already-open window gets it via a
/// `switch-tab` event, since reloading the page would lose its state.
pub fn open_or_focus_settings(app: &AppHandle, title: &str, initial_tab: Option<&str>) {
    if let Some(window) = app.get_webview_window(SETTINGS_WINDOW_LABEL) {
        window.show().ok();
        window.set_focus().ok();
        if let Some(tab) = initial_tab {
            app.emit_to(SETTINGS_WINDOW_LABEL, "switch-tab", tab).ok();
        }
        return;
    }

    let url = match initial_tab {
        Some(tab) => format!("index.html?tab={tab}"),
        None => "index.html".to_string(),
    };
    let result = WebviewWindowBuilder::new(app, SETTINGS_WINDOW_LABEL, WebviewUrl::App(url.into()))
        .title(title)
        .inner_size(480.0, 560.0)
        .resizable(true)
        .center()
        .build();

    if let Err(err) = result {
        log::error!("failed to open settings window: {err}");
    }
}

/// Updates the settings window's title if it's currently open -- called
/// after a UI-language change so the native title bar (which the
/// webview's own re-render can't reach) doesn't stay stale until the
/// window is reopened, per the localization spec's "applies without
/// restart" requirement.
pub fn refresh_title(app: &AppHandle, title: &str) {
    if let Some(window) = app.get_webview_window(SETTINGS_WINDOW_LABEL) {
        window.set_title(title).ok();
    }
}
