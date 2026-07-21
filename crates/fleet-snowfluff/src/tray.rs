//! System tray icon and menu (task 12.1): show/hide, pause/resume,
//! follow-mouse (checked), click-through (checked), settings, quit --
//! labels resolved through the locale dictionary (11.3) and refreshed
//! after every toggle so they always reflect current `PetManager`
//! state, per desktop-integration's "System tray" requirement.

use std::sync::Mutex;

use tauri::{
    menu::{CheckMenuItem, Menu, MenuEvent, MenuItem, PredefinedMenuItem},
    AppHandle, Manager,
};

use crate::{manager::PetManager, settings_window};

/// Handles to the two items whose labels/checked state change at
/// runtime, kept in app-managed state so any code path that mutates
/// `PetManager` (today: only these menu handlers; later: the quick
/// menu and settings webview) can call [`refresh_labels`].
struct TrayItems {
    show_hide: MenuItem<tauri::Wry>,
    pause_resume: MenuItem<tauri::Wry>,
    follow_mouse: CheckMenuItem<tauri::Wry>,
    click_through: CheckMenuItem<tauri::Wry>,
}

fn translate(lang: fleet_snowfluff_core::UiLanguage, key: &str) -> String {
    fleet_snowfluff_core::dictionary(lang).get(key).cloned().unwrap_or_else(|| key.to_string())
}

pub fn build(app: &AppHandle) -> tauri::Result<()> {
    let (lang, paused, visible, follow_mouse, click_through) = {
        let manager = app.state::<Mutex<PetManager>>();
        let m = manager.lock().unwrap();
        (m.ui_language(), m.paused, m.visible(), m.settings.follow_mouse, m.click_through())
    };
    let t = |key: &str| translate(lang, key);

    let show_hide = MenuItem::with_id(
        app,
        "show_hide",
        if visible { t("menu.hide") } else { t("menu.show") },
        true,
        None::<&str>,
    )?;
    let pause_resume = MenuItem::with_id(
        app,
        "pause_resume",
        if paused { t("menu.resume") } else { t("menu.pause") },
        true,
        None::<&str>,
    )?;
    let follow = CheckMenuItem::with_id(
        app,
        "follow_mouse",
        t("menu.follow_mouse"),
        true,
        follow_mouse,
        None::<&str>,
    )?;
    let click = CheckMenuItem::with_id(
        app,
        "click_through",
        t("menu.click_through"),
        true,
        click_through,
        None::<&str>,
    )?;
    let settings_item = MenuItem::with_id(app, "settings", t("menu.settings"), true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", t("menu.quit"), true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;

    let menu = Menu::with_items(
        app,
        &[&show_hide, &pause_resume, &follow, &click, &separator, &settings_item, &quit_item],
    )?;

    app.manage(TrayItems {
        show_hide: show_hide.clone(),
        pause_resume: pause_resume.clone(),
        follow_mouse: follow.clone(),
        click_through: click.clone(),
    });

    // `default_window_icon` is the 512x512 app icon -- fine for a Dock/
    // window icon but oversized for a menu bar status item, so this
    // loads the same icon set's small variant instead.
    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/32x32.png"))
        .expect("icons/32x32.png is a valid bundled PNG");

    tauri::tray::TrayIconBuilder::new()
        .icon(icon)
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(on_menu_event)
        .build(app)?;

    Ok(())
}

fn on_menu_event(app: &AppHandle, event: MenuEvent) {
    let manager = app.state::<Mutex<PetManager>>();
    match event.id().0.as_str() {
        "show_hide" => {
            let mut m = manager.lock().unwrap();
            let next = !m.visible();
            m.set_visible(next);
        }
        "pause_resume" => {
            let mut m = manager.lock().unwrap();
            let next = !m.paused;
            m.set_paused(next);
        }
        "follow_mouse" => {
            let mut m = manager.lock().unwrap();
            m.settings.follow_mouse = !m.settings.follow_mouse;
        }
        "click_through" => {
            let mut m = manager.lock().unwrap();
            let next = !m.click_through();
            m.set_click_through(next);
        }
        "settings" => {
            let title = {
                let m = manager.lock().unwrap();
                translate(m.ui_language(), "settings.window_title")
            };
            settings_window::open_or_focus_settings(app, &title);
            return;
        }
        "quit" => {
            app.exit(0);
            return;
        }
        _ => return,
    }
    refresh_labels(app);
}

fn refresh_labels(app: &AppHandle) {
    let (lang, paused, visible, follow_mouse, click_through) = {
        let manager = app.state::<Mutex<PetManager>>();
        let m = manager.lock().unwrap();
        (m.ui_language(), m.paused, m.visible(), m.settings.follow_mouse, m.click_through())
    };
    let items = app.state::<TrayItems>();
    items
        .show_hide
        .set_text(if visible { translate(lang, "menu.hide") } else { translate(lang, "menu.show") })
        .ok();
    items
        .pause_resume
        .set_text(if paused {
            translate(lang, "menu.resume")
        } else {
            translate(lang, "menu.pause")
        })
        .ok();
    items.follow_mouse.set_checked(follow_mouse).ok();
    items.click_through.set_checked(click_through).ok();
}
