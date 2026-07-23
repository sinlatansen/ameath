//! Linux X11 platform layering (task group 9). Desktop-only (9.1) goes
//! through GTK's own `_NET_WM_WINDOW_TYPE` hint since Tauri's Linux
//! backend is GTK -- no raw X11 needed there. Foreground-window rect
//! detection (9.2), backing both fullscreen-hide and window-snap
//! docking (6.8) exactly like macOS/Windows, has no GTK equivalent at
//! all (GTK only knows about windows *this* app owns, not "what's
//! active on the whole desktop"), so that one goes through a small
//! EWMH client of its own via `x11rb`.
//!
//! Topmost (9.3) and click-through need no code here at all: tao's GTK
//! backend already implements `set_always_on_top` via
//! `gtk::Window::set_keep_above` (which *is* `_NET_WM_STATE_ABOVE`
//! under the hood) and `set_ignore_cursor_events` via an input-shape
//! region, both wired generically through Tauri already -- same
//! situation as Windows (7.3's doc comment).
//!
//! Implemented against the EWMH spec (standardfreedesktop.org's
//! `_NET_ACTIVE_WINDOW`/`_NET_WM_WINDOW_TYPE`/`_NET_WM_STATE`) the same
//! way `wmctrl`/`xdotool` are; unverified on a real GNOME/KDE X11
//! session (task 9.4) since this development environment has no X11
//! display to test against -- `just build-linux`'s container proves it
//! compiles and links, not that a real window manager behaves as
//! expected.

use fleet_snowfluff_core::{Bounds, ForeignWindowRect};
use gtk::prelude::WidgetExt;
use x11rb::{
    connection::Connection,
    protocol::xproto::{AtomEnum, ConnectionExt as _},
    rust_connection::RustConnection,
};

x11rb::atom_manager! {
    Atoms: AtomsCookie {
        _NET_ACTIVE_WINDOW,
        _NET_WM_PID,
    }
}

/// Sets the window's `_NET_WM_WINDOW_TYPE` to `Desktop` -- the X11
/// analog of macOS's `kCGDesktopWindowLevel` and Windows' WorkerW
/// attach, placing it behind normal windows and desktop icons alike.
pub fn set_desktop_level(window: &tauri::window::Window) {
    set_type_hint(window, gdk::WindowTypeHint::Desktop);
}

/// Restores the normal window type (leaving desktop-only mode);
/// `set_always_on_top`/topmost is handled separately by the caller via
/// Tauri's own API, matching macOS/Windows.
pub fn set_normal_level(window: &tauri::window::Window) {
    set_type_hint(window, gdk::WindowTypeHint::Normal);
}

fn set_type_hint(window: &tauri::window::Window, hint: gdk::WindowTypeHint) {
    let Ok(gtk_window) = window.gtk_window() else { return };
    if let Some(gdk_window) = gtk_window.window() {
        gdk_window.set_type_hint(hint);
    }
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

/// Opens a fresh, independent connection to the X server for this one
/// query -- deliberately not reusing GTK's own connection (GDK's Xlib
/// `Display*` isn't something x11rb's XCB-based connection can share
/// cleanly), the same way external tools like `wmctrl`/`xdotool` are
/// separate X clients rather than reaching into a target app's own
/// connection. X11 has no issue with many simultaneous clients.
fn connect_for_query() -> Option<(RustConnection, usize, Atoms)> {
    let (conn, screen_num) = x11rb::connect(None).ok()?;
    let atoms = Atoms::new(&conn).ok()?.reply().ok()?;
    Some((conn, screen_num, atoms))
}

/// The frontmost normal on-screen window that isn't ours, with its
/// bounds in the same logical coordinate space as [`Bounds`]/window
/// positioning. `None` if there isn't one, it's ours, or window info
/// couldn't be read (e.g. no X11 display, or the WM doesn't implement
/// `_NET_ACTIVE_WINDOW`).
pub fn foreground_window() -> Option<ForegroundWindow> {
    let (conn, screen_num, atoms) = connect_for_query()?;
    let root = conn.setup().roots.get(screen_num)?.root;

    let active_reply = conn
        .get_property(false, root, atoms._NET_ACTIVE_WINDOW, AtomEnum::WINDOW, 0, 1)
        .ok()?
        .reply()
        .ok()?;
    let active = active_reply.value32()?.next()?;
    if active == 0 {
        return None;
    }

    let our_pid = std::process::id();
    let pid_reply = conn
        .get_property(false, active, atoms._NET_WM_PID, AtomEnum::CARDINAL, 0, 1)
        .ok()?
        .reply()
        .ok();
    if let Some(pid) = pid_reply.and_then(|r| r.value32().and_then(|mut it| it.next())) {
        if pid == our_pid {
            return None;
        }
    }

    let geometry = conn.get_geometry(active).ok()?.reply().ok()?;
    // `GetGeometry`'s x/y are relative to the window's immediate
    // parent -- for a reparenting WM that's the decoration frame, not
    // the root window -- so translate to root-relative (screen)
    // coordinates instead of using them directly.
    let translated = conn.translate_coordinates(active, root, 0, 0).ok()?.reply().ok()?;
    let (x, y) = (translated.dst_x as f64, translated.dst_y as f64);
    let (w, h) = (geometry.width as f64, geometry.height as f64);

    Some(ForegroundWindow {
        rect: ForeignWindowRect { left: x, top: y, right: x + w, bottom: y + h },
    })
}
