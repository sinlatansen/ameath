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
        Graphics::{
            Dwm::{DwmEnableBlurBehindWindow, DWM_BB_ENABLE, DWM_BLURBEHIND},
            Gdi::HRGN,
        },
        UI::{
            HiDpi::GetDpiForWindow,
            WindowsAndMessaging::{
                EnumWindows, FindWindowExW, FindWindowW, GetClassNameW, GetForegroundWindow,
                GetParent, GetWindowLongPtrW, GetWindowRect, GetWindowThreadProcessId,
                SendMessageTimeoutW, SetParent, SetWindowLongPtrW, SetWindowPos, GWL_EXSTYLE,
                HWND_BOTTOM, SMTO_NORMAL, SWP_FRAMECHANGED, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
                SWP_NOZORDER, WS_EX_NOREDIRECTIONBITMAP,
            },
        },
    },
};

/// Sets `WS_EX_NOREDIRECTIONBITMAP` on `window`, which the DirectComposition-
/// backed transparent surface (design.md D14, task 3.1) requires per
/// Microsoft's own docs: without it, DXGI creates a normal GDI-redirected
/// swapchain that doesn't support the alpha-compositing modes wgpu asks
/// for (`pick_alpha_mode` in gfx.rs), silently falling back to
/// `CompositeAlphaMode::Opaque` -- an opaque rectangle behind the sprite.
///
/// Two things Tauri's cross-platform `WindowBuilder` doesn't expose (tao's
/// own `WindowBuilderExtWindows::with_no_redirection_bitmap` isn't
/// reachable through it) have to be corrected for after the fact here:
///
/// 1. Because `no_redirection_bitmap` was never set at window-creation time,
///    tao's own window-creation code (seeing `transparent(true)` with that flag
///    unset) already called `DwmEnableBlurBehindWindow` with a full-window blur
///    region -- the older, DWM-composited transparency mechanism, and a real
///    source of visible flicker and a shadow-like edge glow on some driver/DWM
///    combinations. That call already happened by the time this function runs,
///    so it has to be explicitly undone (`fEnable: false`), not just skipped.
/// 2. `SetWindowLongPtrW` alone changes the style bit but Windows doesn't
///    necessarily re-evaluate the window's redirection surface just because of
///    that -- `SetWindowPos(..., SWP_FRAMECHANGED)` is the standard way to
///    force a re-evaluation after an extended-style change (the same pattern
///    legacy's `window_manager.py` used for its own `SetWindowLongW` calls).
///
/// Must run before the wgpu surface is created against this window,
/// since wgpu picks its swapchain creation path by inspecting the
/// window's style bits at that point.
pub fn enable_composition_swapchain(window: &tauri::window::Window) {
    let Some(hwnd) = hwnd_of(window) else { return };
    unsafe {
        let disable_blur = DWM_BLURBEHIND {
            dwFlags: DWM_BB_ENABLE,
            fEnable: false.into(),
            hRgnBlur: HRGN::default(),
            fTransitionOnMaximized: false.into(),
        };
        let _ = DwmEnableBlurBehindWindow(hwnd, &disable_blur);

        let current = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, current | WS_EX_NOREDIRECTIONBITMAP.0 as isize);
        let _ = SetWindowPos(
            hwnd,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );
    }
}

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
