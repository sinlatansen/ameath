//! Opens (or focuses) the settings webview window (task 12.1/12.3):
//! shared by the tray's Settings item, the quick menu's, and the
//! auto-update startup check (14.2), since the settings-ui spec
//! requires only one instance to ever exist regardless of entry point.
//!
//! This is the app's only webview, so it's the one place that cares
//! whether the binary was built through the Tauri CLI. `WebviewUrl::
//! App` resolves to `devUrl` (http://localhost:1420) whenever the
//! `tauri` crate's `custom-protocol` feature is off, which is the case
//! for a plain `cargo run`/`cargo build` -- only `cargo tauri dev`
//! (via `beforeDevCommand`, which actually starts that Vite server) or
//! `cargo tauri build` (which turns `custom-protocol` on and serves
//! the embedded `frontendDist` instead) get this right. Always use
//! `just dev` / `just build`, never a raw cargo invocation, or this
//! window loads nothing and the page is silently blank.

use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

const SETTINGS_WINDOW_LABEL: &str = "settings";

/// Opens the settings window, or focuses it if already open.
/// `initial_tab` requests which tab should be active -- `None` leaves
/// it wherever the window currently defaults to; `Some("update")` is
/// how the startup update check (14.2) asks for the update tab. Always
/// loads the same plain `index.html` with no query string appended --
/// not needed to pass `initial_tab` through (see `pending_update` in
/// commands.rs) and better not to rely on `WebviewUrl::App`'s handling
/// of a path that isn't exactly the literal string `"index.html"`
/// rather than find out the hard way it doesn't work like a normal
/// URL's query string would. For an already-open window, `initial_tab`
/// is delivered via a `switch-tab` event; a freshly created window
/// instead reads the pending update straight from `pending_update` on
/// load, since there's no listener registered yet to catch an event
/// fired this early.
pub fn open_or_focus_settings(app: &AppHandle, title: &str, initial_tab: Option<&str>) {
    if let Some(window) = app.get_webview_window(SETTINGS_WINDOW_LABEL) {
        window.show().ok();
        window.set_focus().ok();
        if let Some(tab) = initial_tab {
            app.emit_to(SETTINGS_WINDOW_LABEL, "switch-tab", tab).ok();
        }
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
