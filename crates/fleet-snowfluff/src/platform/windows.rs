//! Windows platform layering (tasks 7.1/7.2): desktop-only placement via
//! WorkerW attachment and foreground-window-rect fullscreen/dock
//! detection, porting `legacy/ameath/window_manager.py`'s Win32 calls.
//! Topmost (7.3) and click-through are already covered generically by
//! `tauri::window::Window::set_always_on_top`/`set_ignore_cursor_events`
//! -- tao's Windows backend implements both with the same
//! `SetWindowPos`/`WS_EX_LAYERED|WS_EX_TRANSPARENT` mechanism legacy used
//! by hand -- so this module only needs the two things Tauri doesn't
//! expose.

use fleet_snowfluff_core::{Bounds, ForeignWindowRect};
use windows::{
    core::HSTRING,
    Win32::{
        Foundation::{HWND, LPARAM, RECT, WPARAM},
        UI::{
            HiDpi::GetDpiForWindow,
            WindowsAndMessaging::{
                EnumWindows, FindWindowExW, FindWindowW, GetClassNameW, GetForegroundWindow,
                GetParent, GetWindowRect, GetWindowThreadProcessId, SendMessageTimeoutW, SetParent,
                SetWindowPos, HWND_BOTTOM, SMTO_NORMAL, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
            },
        },
    },
};

// A `WS_EX_NOREDIRECTIONBITMAP` + `DwmEnableBlurBehindWindow(fEnable: false)`
// + `SetWindowPos(SWP_FRAMECHANGED)` attempt at fixing the transparent pet
// windows' flicker/shadow (design.md D14, task 3.1) was tried and reverted
// here -- reported back as making it *worse* (a solid black box instead of
// the previous shadow/blink). Most likely explanation:
// `WS_EX_NOREDIRECTIONBITMAP` tells Windows not to maintain a redirection
// bitmap for the window at all, which is only useful if something else (a
// DirectComposition visual tree, via `IDCompositionVisual`/
// `IDCompositionTarget`) is explicitly wired up to present content instead --
// wgpu's own Windows surface creation doesn't appear to do that automatically
// from just the style bit being set, so DWM had nothing to composite. Properly
// using DirectComposition here would mean driving those COM APIs directly
// rather than a style-bit shortcut, which is a real rewrite (arguably what task
// 3.5's "fall back to UpdateLayeredWindow" escape hatch was anticipating), not
// a follow-up tweak -- left for a dedicated attempt with real Windows hardware
// to verify against, informed by the wgpu alpha-mode log line (gfx.rs's
// `pick_alpha_mode`) now retrievable via lib.rs's always-on file logging.

const WM_TRIGGER_WORKERW: u32 = 0x052c;

fn hwnd_of(window: &tauri::window::Window) -> Option<HWND> { window.hwnd().ok() }

fn class_name(hwnd: HWND) -> String {
    let mut buf = [0u16; 256];
    let len = unsafe { GetClassNameW(hwnd, &mut buf) };
    String::from_utf16_lossy(&buf[..len.max(0) as usize])
}

/// Finds the desktop-icon `WorkerW` (the empty one behind
/// `SHELLDLL_DefView`, not the one containing it) that pet windows
/// should attach to, mirroring `window_manager.py`'s `get_desktop_workerw`.
fn desktop_workerw() -> Option<HWND> {
    let progman = unsafe { FindWindowW(&HSTRING::from("Progman"), None) }.ok()?;

    // Undocumented but widely relied-upon message that makes Explorer spawn
    // a WorkerW behind the desktop icons on Windows 8+ (same trigger
    // legacy used); timeout matches legacy's 1000ms.
    unsafe {
        let _ = SendMessageTimeoutW(
            progman,
            WM_TRIGGER_WORKERW,
            WPARAM(0),
            LPARAM(0),
            SMTO_NORMAL,
            1000,
            None,
        );
    }

    let mut found = None;
    unsafe extern "system" fn enum_proc(hwnd: HWND, lparam: LPARAM) -> windows::core::BOOL {
        let out = lparam.0 as *mut Option<HWND>;
        let shell =
            unsafe { FindWindowExW(Some(hwnd), None, &HSTRING::from("SHELLDLL_DefView"), None) };
        if shell.is_ok() {
            if let Ok(workerw) =
                unsafe { FindWindowExW(None, Some(hwnd), &HSTRING::from("WorkerW"), None) }
            {
                unsafe { *out = Some(workerw) };
            }
        }
        true.into()
    }
    unsafe {
        let _ = EnumWindows(Some(enum_proc), LPARAM(&mut found as *mut _ as isize));
    }
    found
}

/// Attaches `window` to the desktop's `WorkerW` and drops it to the
/// bottom of that parent's z-order -- legacy's "desktop-only" mode.
/// No-op (returns without effect) if the WorkerW can't be found, e.g. on
/// a Windows version where Explorer doesn't create one this way.
pub fn set_desktop_level(window: &tauri::window::Window) {
    let Some(hwnd) = hwnd_of(window) else { return };
    let Some(workerw) = desktop_workerw() else { return };
    unsafe {
        let _ = SetParent(hwnd, Some(workerw));
        let _ = SetWindowPos(
            hwnd,
            Some(HWND_BOTTOM),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        );
    }
}

/// Detaches `window` from `WorkerW` if it's currently parented there,
/// restoring it as a normal top-level window (legacy's
/// `detach_from_desktop`). Safe to call unconditionally: a no-op if the
/// window isn't attached.
pub fn set_normal_level(window: &tauri::window::Window) {
    let Some(hwnd) = hwnd_of(window) else { return };
    let Ok(parent) = (unsafe { GetParent(hwnd) }) else { return };
    if class_name(parent) == "WorkerW" {
        unsafe {
            let _ = SetParent(hwnd, None);
        }
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

/// The frontmost window that isn't the desktop shell (`Progman`/
/// `WorkerW`) or one of our own pet windows, with its bounds converted
/// from physical pixels (what `GetWindowRect` reports) to the logical
/// points every other `Bounds`/window-position value in this codebase
/// uses -- via the foreground window's own per-monitor DPI, since it may
/// sit on a different-scaled monitor than any of ours.
pub fn foreground_window() -> Option<ForegroundWindow> {
    let hwnd = unsafe { GetForegroundWindow() };
    if hwnd.is_invalid() {
        return None;
    }
    let name = class_name(hwnd);
    if name == "Progman" || name == "WorkerW" {
        return None;
    }

    let mut owner_pid = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd, Some(&mut owner_pid)) };
    if owner_pid == std::process::id() {
        return None;
    }

    let mut rect = RECT::default();
    unsafe { GetWindowRect(hwnd, &mut rect) }.ok()?;

    let dpi = unsafe { GetDpiForWindow(hwnd) };
    let scale = if dpi == 0 { 1.0 } else { dpi as f64 / 96.0 };

    Some(ForegroundWindow {
        rect: ForeignWindowRect {
            left: rect.left as f64 / scale,
            top: rect.top as f64 / scale,
            right: rect.right as f64 / scale,
            bottom: rect.bottom as f64 / scale,
        },
    })
}
