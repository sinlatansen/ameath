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
    // Diagnostic (not permanent): reports of right-click doing nothing
    // on Windows with no visible error anywhere -- `menu.popup` returns
    // `tauri::Result<()>` that success/failure alone can't distinguish
    // from "opened and was instantly dismissed" (e.g. if `TrackPopupMenu`
    // ends up with a `SetForegroundWindow` that Windows silently refused,
    // since this popup is triggered by our own background mouse-polling
    // loop rather than a real input message the window received). These
    // logs exist to tell those two cases apart on the next real-hardware
    // test.
    log::info!("quick menu requested for window {:?}", window.label());
    match crate::tray::build_menu(app) {
        Ok((menu, _items)) => match menu.popup(window.clone()) {
            Ok(()) => log::info!("quick menu popup() returned Ok for window {:?}", window.label()),
            Err(err) => log::error!("quick menu popup() failed for {:?}: {err}", window.label()),
        },
        Err(err) => log::error!("failed to build quick menu: {err}"),
    }
}
