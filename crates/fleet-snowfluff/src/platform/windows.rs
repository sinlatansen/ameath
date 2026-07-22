//! Windows platform layering (tasks 7.1/7.2): desktop-only placement via
//! WorkerW attachment and foreground-window-rect fullscreen/dock
//! detection, porting `legacy/ameath/window_manager.py`'s Win32 calls.
//! Topmost (7.3) and click-through are already covered generically by
//! `tauri::window::Window::set_always_on_top`/`set_ignore_cursor_events`
//! -- tao's Windows backend implements both with the same
//! `SetWindowPos`/`WS_EX_LAYERED|WS_EX_TRANSPARENT` mechanism legacy used
//! by hand.
//!
//! Also owns pet-window rendering on this platform ([`LayeredSurface`]),
//! which is unrelated to the WorkerW/foreground-window stuff above but
//! lives here since it's equally Windows-specific. Two earlier attempts
//! at getting wgpu's swapchain to composite transparently (a
//! `WS_EX_NOREDIRECTIONBITMAP` + DirectComposition-adjacent style-bit
//! hack, then just trying the DX12 backend instead of Vulkan) both
//! failed -- real hardware testing showed `wgpu alpha modes available`
//! reporting `Opaque`-only under *both* backends, meaning the swapchain
//! genuinely has no per-pixel alpha compositing support through
//! whatever surface Tauri's window creation path hands wgpu. That's
//! also almost certainly why memory usage stayed high (a full DX12/
//! Vulkan device + swapchain per pet window, never actually buying any
//! transparency) and why many instances made the tray menu/settings
//! window "stuck" (every pet's `present()` call runs on the same main
//! thread the OS-level UI needs).
//!
//! `UpdateLayeredWindow` is the classic, pre-DWM-composition Win32 API
//! for exactly this (a small always-on-top sprite with real per-pixel
//! alpha) -- no GPU pipeline at all, just a GDI memory DC blitted
//! straight onto the window. It's what legacy Ameath was reaching for
//! with tkinter's `-transparentcolor` (`legacy/ameath/constants.py`'s
//! `TRANSPARENT_COLOR`), except that's chroma-key (binary transparent/
//! opaque, jagged edges) where this uses the GIFs' real alpha channel.

use fleet_snowfluff_core::{Bounds, ForeignWindowRect};
use windows::{
    core::HSTRING,
    Win32::{
        Foundation::{COLORREF, HWND, LPARAM, POINT, RECT, SIZE, WPARAM},
        Graphics::Gdi::{
            CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, SelectObject,
            AC_SRC_ALPHA, AC_SRC_OVER, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, BLENDFUNCTION,
            DIB_RGB_COLORS, HBITMAP, HDC,
        },
        UI::{
            HiDpi::GetDpiForWindow,
            WindowsAndMessaging::{
                EnumWindows, FindWindowExW, FindWindowW, GetClassNameW, GetForegroundWindow,
                GetParent, GetWindowLongPtrW, GetWindowRect, GetWindowThreadProcessId,
                SendMessageTimeoutW, SetParent, SetWindowLongPtrW, SetWindowPos,
                UpdateLayeredWindow, GWL_EXSTYLE, HWND_BOTTOM, SMTO_NORMAL, SWP_NOACTIVATE,
                SWP_NOMOVE, SWP_NOSIZE, ULW_ALPHA, WS_EX_LAYERED,
            },
        },
    },
};

const WM_TRIGGER_WORKERW: u32 = 0x052c;

fn hwnd_of(window: &tauri::window::Window) -> Option<HWND> { window.hwnd().ok() }

fn class_name(hwnd: HWND) -> String {
    let mut buf = [0u16; 256];
    let len = unsafe { GetClassNameW(hwnd, &mut buf) };
    String::from_utf16_lossy(&buf[..len.max(0) as usize])
}

/// Sets `WS_EX_LAYERED` on `window`, required for [`LayeredSurface::update`]
/// (`UpdateLayeredWindow`) to have any effect. Call once, right after
/// creation, instead of the builder's `.transparent(true)` -- that flag
/// routes through tao's DWM-blur-behind transparency path, a different
/// (and, per the module doc, not-working-for-us) mechanism that fights
/// with this one rather than complementing it.
pub fn make_layered(window: &tauri::window::Window) {
    let Some(hwnd) = hwnd_of(window) else { return };
    unsafe {
        let current = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED.0 as isize);
    }
}

/// The GDI memory DC + 32bpp top-down DIB section backing one pet
/// window's [`update`](Self::update) calls, cached across frames the
/// same way `gfx.rs`'s wgpu texture is -- rebuilt only when the pixel
/// dimensions change, not on every frame.
#[derive(Default)]
pub struct LayeredSurface {
    mem_dc: HDC,
    bitmap: HBITMAP,
    pixels: *mut u8,
    width: u32,
    height: u32,
}

// SAFETY: a `LayeredSurface` is only ever touched from the main thread
// (constructed and updated from `PetWindow`, itself only ever touched
// while holding `Mutex<PetManager>` from the tick callback that always
// runs via `run_on_main_thread`) -- the raw GDI handles and pointer
// inside are never actually accessed concurrently, `Send` just isn't
// derivable automatically for raw pointers.
unsafe impl Send for LayeredSurface {}

impl Drop for LayeredSurface {
    fn drop(&mut self) {
        unsafe {
            if !self.bitmap.is_invalid() {
                let _ = DeleteObject(self.bitmap.into());
            }
            if !self.mem_dc.is_invalid() {
                let _ = DeleteDC(self.mem_dc);
            }
        }
    }
}

impl LayeredSurface {
    fn ensure_size(&mut self, width: u32, height: u32) {
        if self.width == width && self.height == height && !self.mem_dc.is_invalid() {
            return;
        }
        unsafe {
            if !self.bitmap.is_invalid() {
                let _ = DeleteObject(self.bitmap.into());
            }
            if self.mem_dc.is_invalid() {
                self.mem_dc = CreateCompatibleDC(None);
            }
            let bmi = BITMAPINFO {
                bmiHeader: BITMAPINFOHEADER {
                    biSize: size_of::<BITMAPINFOHEADER>() as u32,
                    biWidth: width as i32,
                    // Negative height selects top-down row order, matching
                    // how `frame.rgba` is already laid out (row 0 first).
                    biHeight: -(height as i32),
                    biPlanes: 1,
                    biBitCount: 32,
                    biCompression: BI_RGB.0,
                    ..Default::default()
                },
                ..Default::default()
            };
            let mut bits: *mut core::ffi::c_void = std::ptr::null_mut();
            let Ok(bitmap) =
                CreateDIBSection(Some(self.mem_dc), &bmi, DIB_RGB_COLORS, &mut bits, None, 0)
            else {
                log::error!("failed to create DIB section for layered pet window");
                return;
            };
            SelectObject(self.mem_dc, bitmap.into());
            self.bitmap = bitmap;
            self.pixels = bits as *mut u8;
            self.width = width;
            self.height = height;
        }
    }

    /// Scales `frame_rgba` (straight-alpha, `frame_w x frame_h`, the
    /// GIF's native pixel size) to `scaled_w x scaled_h` (that size
    /// times the user's scale setting -- the wgpu path gets this for
    /// free from the shader stretching a native-res texture over a
    /// scaled surface; GDI has no equivalent, so it's done by hand
    /// here, nearest-neighbor to match `gfx.rs`'s sampler filter mode),
    /// converts to premultiplied BGRA (what `AC_SRC_ALPHA` requires),
    /// and blits via `UpdateLayeredWindow` at logical position `(x, y)`
    /// -- converted, like `scaled_w`/`scaled_h`, to this window's own
    /// physical pixels first. `UpdateLayeredWindow` isn't DPI-aware on
    /// its own (unlike every other window call in this codebase, which
    /// goes through Tauri's `Position::Logical`/`Size::Logical` and
    /// gets this conversion for free) -- both the position *and* the
    /// size need it, or the pet renders at the wrong scale the moment
    /// it's on a different monitor than whichever one the numbers
    /// happened to already be correct for.
    #[allow(clippy::too_many_arguments)]
    pub fn update(
        &mut self,
        window: &tauri::window::Window,
        frame_rgba: &[u8],
        frame_w: u32,
        frame_h: u32,
        scaled_w: u32,
        scaled_h: u32,
        x: f64,
        y: f64,
        opacity: f32,
    ) {
        let Some(hwnd) = hwnd_of(window) else { return };
        if scaled_w == 0 || scaled_h == 0 || frame_w == 0 || frame_h == 0 {
            return;
        }

        let dpi = unsafe { GetDpiForWindow(hwnd) };
        let dpi_scale = if dpi == 0 { 1.0 } else { dpi as f64 / 96.0 };
        let physical_w = ((scaled_w as f64) * dpi_scale).round() as u32;
        let physical_h = ((scaled_h as f64) * dpi_scale).round() as u32;
        if physical_w == 0 || physical_h == 0 {
            return;
        }

        self.ensure_size(physical_w, physical_h);
        if self.pixels.is_null() {
            return;
        }

        let dst = unsafe {
            std::slice::from_raw_parts_mut(self.pixels, (physical_w * physical_h * 4) as usize)
        };
        for dst_y in 0..physical_h {
            let src_y = (dst_y * frame_h / physical_h).min(frame_h - 1);
            for dst_x in 0..physical_w {
                let src_x = (dst_x * frame_w / physical_w).min(frame_w - 1);
                let src_off = ((src_y * frame_w + src_x) * 4) as usize;
                let dst_off = ((dst_y * physical_w + dst_x) * 4) as usize;
                let (r, g, b, a) = (
                    frame_rgba[src_off] as u32,
                    frame_rgba[src_off + 1] as u32,
                    frame_rgba[src_off + 2] as u32,
                    frame_rgba[src_off + 3] as u32,
                );
                // BGRA order, premultiplied -- what a 32bpp DIB used
                // with AC_SRC_ALPHA requires.
                dst[dst_off] = (b * a / 255) as u8;
                dst[dst_off + 1] = (g * a / 255) as u8;
                dst[dst_off + 2] = (r * a / 255) as u8;
                dst[dst_off + 3] = a as u8;
            }
        }

        let dst_pos =
            POINT { x: (x * dpi_scale).round() as i32, y: (y * dpi_scale).round() as i32 };
        let size = SIZE { cx: physical_w as i32, cy: physical_h as i32 };
        let src_pos = POINT { x: 0, y: 0 };
        let blend = BLENDFUNCTION {
            BlendOp: AC_SRC_OVER as u8,
            BlendFlags: 0,
            SourceConstantAlpha: (opacity.clamp(0.0, 1.0) * 255.0).round() as u8,
            AlphaFormat: AC_SRC_ALPHA as u8,
        };
        unsafe {
            let _ = UpdateLayeredWindow(
                hwnd,
                None,
                Some(&dst_pos),
                Some(&size),
                Some(self.mem_dc),
                Some(&src_pos),
                COLORREF(0),
                Some(&blend),
                ULW_ALPHA,
            );
        }
    }
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
