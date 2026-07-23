//! macOS platform layering (tasks 8.1-8.3): desktop-level window
//! placement (`kCGDesktopWindowLevel`) and topmost/click-through are
//! straightforward -- Tauri already exposes `set_always_on_top` and
//! `set_ignore_cursor_events` directly, and the raw `NSWindow` pointer
//! via `ns_window()` for the one thing it doesn't (arbitrary window
//! levels).
//!
//! [`foreground_window`] backs both fullscreen-hide detection (8.2) and
//! window-snap docking (6.8): both need "what's the frontmost normal
//! window and where is it", so they share one `CGWindowListCopyWindowInfo`
//! query rather than two.

use core_foundation::{
    array::CFArray,
    base::{CFType, TCFType},
    dictionary::{CFDictionary, CFDictionaryRef},
    number::CFNumber,
    string::CFString,
};
use core_graphics::window::{
    copy_window_info, kCGNullWindowID, kCGWindowBounds, kCGWindowLayer,
    kCGWindowListExcludeDesktopElements, kCGWindowListOptionOnScreenOnly, kCGWindowOwnerPID,
};
use fleet_snowfluff_core::{Bounds, ForeignWindowRect};
use objc2_app_kit::{NSWindow, NSWindowLevel};

/// Places the window at the desktop layer, behind all normal app
/// windows -- the macOS equivalent of legacy's WorkerW attachment.
pub fn set_desktop_level(window: &tauri::window::Window) {
    set_level(window, unsafe { CGWindowLevelForKey(2) }); // kCGDesktopWindowLevelKey
}

/// Restores the normal window level (used when leaving desktop-only
/// mode; `set_always_on_top`/topmost is handled separately by the
/// caller via Tauri's own API).
pub fn set_normal_level(window: &tauri::window::Window) {
    set_level(window, unsafe { CGWindowLevelForKey(4) }); // kCGNormalWindowLevelKey
}

fn set_level(window: &tauri::window::Window, level: i32) {
    let Ok(ptr) = window.ns_window() else { return };
    if ptr.is_null() {
        return;
    }
    let ns_window = ptr as *mut NSWindow;
    unsafe {
        (*ns_window).setLevel(level as NSWindowLevel);
    }
}

// `key` must be a valid `CGWindowLevelKey` value (see Apple's
// `CGWindowLevel.h`); these keys are stable across macOS versions, the
// resulting level integers are not, hence calling this instead of
// hardcoding a level.
#[link(name = "CoreGraphics", kind = "framework")]
unsafe extern "C" {
    fn CGWindowLevelForKey(key: i32) -> i32;
}

pub struct ForegroundWindow {
    pub rect: ForeignWindowRect,
}

impl ForegroundWindow {
    /// True if this window's bounds cover the whole of `screen`,
    /// matching legacy's fullscreen-hide heuristic (width/height >=
    /// screen dimensions).
    pub fn covers(&self, screen: Bounds) -> bool {
        (self.rect.right - self.rect.left) >= screen.width()
            && (self.rect.bottom - self.rect.top) >= screen.height()
    }
}

/// The frontmost normal (layer 0) on-screen window that isn't ours,
/// with its bounds in the same logical coordinate space as
/// [`Bounds`]/window positioning. `None` if there isn't one (e.g. only
/// the desktop is showing) or window info couldn't be read.
pub fn foreground_window() -> Option<ForegroundWindow> {
    let our_pid = std::process::id() as i64;
    let options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements;
    let array: CFArray = copy_window_info(options, kCGNullWindowID)?;

    for item in array.iter() {
        let dict_ref = *item as CFDictionaryRef;
        if dict_ref.is_null() {
            continue;
        }
        let dict: CFDictionary<CFString, CFType> =
            unsafe { CFDictionary::wrap_under_get_rule(dict_ref) };

        let layer = dict
            .find(unsafe { kCGWindowLayer })
            .and_then(|v| v.downcast::<CFNumber>())
            .and_then(|n| n.to_i64());
        if layer != Some(0) {
            continue;
        }

        let owner_pid = dict
            .find(unsafe { kCGWindowOwnerPID })
            .and_then(|v| v.downcast::<CFNumber>())
            .and_then(|n| n.to_i64());
        if owner_pid == Some(our_pid) {
            continue;
        }

        // `ConcreteCFType` is only implemented for the raw-pointer form;
        // downcast to that, then re-wrap as a typed dictionary the same
        // way the outer `dict` was built above.
        let raw_bounds_dict = dict.find(unsafe { kCGWindowBounds }).and_then(|v| {
            v.downcast::<CFDictionary<*const std::ffi::c_void, *const std::ffi::c_void>>()
        });
        let Some(raw_bounds_dict) = raw_bounds_dict else { continue };
        let bounds_dict: CFDictionary<CFString, CFType> = unsafe {
            CFDictionary::wrap_under_get_rule(
                raw_bounds_dict.as_concrete_TypeRef() as CFDictionaryRef
            )
        };

        let get = |key: &str| -> Option<f64> {
            bounds_dict
                .find(CFString::new(key))
                .and_then(|v| v.downcast::<CFNumber>())
                .and_then(|n| n.to_f64())
        };
        let (Some(x), Some(y), Some(w), Some(h)) =
            (get("X"), get("Y"), get("Width"), get("Height"))
        else {
            continue;
        };

        return Some(ForegroundWindow {
            rect: ForeignWindowRect { left: x, top: y, right: x + w, bottom: y + h },
        });
    }
    None
}
