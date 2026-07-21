//! Right-click quick menu on a pet (task 12.2): a native OS context
//! menu mirroring the tray's items, per desktop-integration's "Quick
//! context menu" requirement. Reuses `tray::build_menu` for the exact
//! same item list/labels/order rather than duplicating it, and relies
//! on the tray's already-registered `on_menu_event` handler to route
//! clicks -- Tauri delivers menu events globally regardless of which
//! menu (tray or an ad-hoc popup like this one) they came from.

use tauri::{menu::ContextMenu, AppHandle};

/// Shows the quick menu at the cursor, anchored to `window` (the pet
/// that was right-clicked). Blocks the calling thread until the menu
/// is dismissed -- `PetManager::tick` calls this inline on the main
/// thread, which is exactly the native, expected behavior for a modal
/// context menu (and freezes that pet's pose while it's open, matching
/// legacy's temporary-pause-on-open).
pub fn popup(app: &AppHandle, window: &tauri::window::Window) {
    match crate::tray::build_menu(app) {
        Ok((menu, _items)) => {
            menu.popup(window.clone()).ok();
        }
        Err(err) => log::error!("failed to build quick menu: {err}"),
    }
}
