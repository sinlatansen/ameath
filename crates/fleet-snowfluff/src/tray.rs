//! System tray icon and menu (task 12.1): show/hide, pause/resume,
//! follow-mouse (checked), click-through (checked), settings, quit --
//! labels resolved through the locale dictionary (11.3) and refreshed
//! after every toggle so they always reflect current `PetManager`
//! state, per desktop-integration's "System tray" requirement.

use std::sync::Mutex;

use tauri::{
    menu::{CheckMenuItem, IsMenuItem, Menu, MenuEvent, MenuItem, PredefinedMenuItem},
    AppHandle, Manager,
};

use crate::{manager::PetManager, settings_window};

/// Every item in the show/hide, pause/resume, follow-mouse,
/// click-through, settings, quit menu (desktop-integration spec: tray
/// and quick menu mirror each other). Built fresh from current
/// `PetManager` state each time -- the tray keeps one of these long
/// enough to refresh labels on toggle (12.1); the quick menu (12.2)
/// builds one, pops it up, and lets it drop once dismissed.
pub(crate) struct MenuItemSet {
    show_hide: MenuItem<tauri::Wry>,
    pause_resume: MenuItem<tauri::Wry>,
    follow_mouse: CheckMenuItem<tauri::Wry>,
    click_through: CheckMenuItem<tauri::Wry>,
    settings: MenuItem<tauri::Wry>,
    quit: MenuItem<tauri::Wry>,
    separator: PredefinedMenuItem<tauri::Wry>,
}

impl MenuItemSet {
    fn build(app: &AppHandle) -> tauri::Result<Self> {
        let (lang, paused, visible, follow_mouse, click_through) = {
            let manager = app.state::<Mutex<PetManager>>();
            let m = manager.lock().unwrap();
            (m.ui_language(), m.paused, m.visible(), m.settings.follow_mouse, m.click_through())
        };
        let t = |key: &str| translate(lang, key);

        Ok(Self {
            show_hide: MenuItem::with_id(
                app,
                "show_hide",
                if visible { t("menu.hide") } else { t("menu.show") },
                true,
                None::<&str>,
            )?,
            pause_resume: MenuItem::with_id(
                app,
                "pause_resume",
                if paused { t("menu.resume") } else { t("menu.pause") },
                true,
                None::<&str>,
            )?,
            follow_mouse: CheckMenuItem::with_id(
                app,
                "follow_mouse",
                t("menu.follow_mouse"),
                true,
                follow_mouse,
                None::<&str>,
            )?,
            click_through: CheckMenuItem::with_id(
                app,
                "click_through",
                t("menu.click_through"),
                true,
                click_through,
                None::<&str>,
            )?,
            settings: MenuItem::with_id(app, "settings", t("menu.settings"), true, None::<&str>)?,
            quit: MenuItem::with_id(app, "quit", t("menu.quit"), true, None::<&str>)?,
            separator: PredefinedMenuItem::separator(app)?,
        })
    }

    fn as_refs(&self) -> [&dyn IsMenuItem<tauri::Wry>; 7] {
        [
            &self.show_hide,
            &self.pause_resume,
            &self.follow_mouse,
            &self.click_through,
            &self.separator,
            &self.settings,
            &self.quit,
        ]
    }
}

/// Builds a menu snapshotting current `PetManager` state -- shared by
/// the tray (12.1) and the quick menu (12.2) so both stay in lockstep
/// with exactly one place that knows the item list, order, and labels.
pub(crate) fn build_menu(app: &AppHandle) -> tauri::Result<(Menu<tauri::Wry>, MenuItemSet)> {
    let items = MenuItemSet::build(app)?;
    let menu = Menu::with_items(app, &items.as_refs())?;
    Ok((menu, items))
}

fn translate(lang: fleet_snowfluff_core::UiLanguage, key: &str) -> String {
    fleet_snowfluff_core::dictionary(lang).get(key).cloned().unwrap_or_else(|| key.to_string())
}

pub fn build(app: &AppHandle) -> tauri::Result<()> {
    let (menu, items) = build_menu(app)?;
    app.manage(items);

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
    let items = app.state::<MenuItemSet>();
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
