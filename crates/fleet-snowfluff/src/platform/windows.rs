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
        Graphics::{
            Dwm::{DwmSetWindowAttribute, DWMWA_TRANSITIONS_FORCEDISABLED},
            Gdi::{
                CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, SelectObject,
                AC_SRC_ALPHA, AC_SRC_OVER, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, BLENDFUNCTION,
                DIB_RGB_COLORS, HBITMAP, HDC, HGDIOBJ,
            },
        },
        UI::{
            HiDpi::{
                GetDpiForWindow, SetThreadDpiAwarenessContext,
                DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
            },
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

/// Finds which monitor's logical bounds contain logical point `(x, y)`
/// and returns that monitor's own scale factor together with the
/// point's physical-pixel equivalent -- unlike a plain size multiply
/// (fine for `SIZE`, which has no origin to get wrong), a *position* on
/// a multi-monitor desktop mixing DPIs isn't related to its physical
/// counterpart by a single global scalar: each monitor's logical origin
/// only lines up with its physical origin if it happens to sit at the
/// virtual desktop's origin. `manager.rs`'s `physical_to_logical_cursor`
/// is the same fix in the opposite direction, for the same reason.
///
/// Returning the scale here too (rather than having the caller separately
/// call `GetDpiForWindow` for sizing) matters, not just for convenience:
/// `GetDpiForWindow` reflects whichever monitor Windows currently
/// considers the window to be on, which lags one frame behind a window
/// that's actively moving -- using it for size while this function's
/// own fresh monitor lookup is used for position meant size and
/// position could each be computed against a *different* monitor's
/// scale right as a window crosses a boundary, which is exactly the
/// kind of inconsistency that made Windows itself flip-flop the
/// window's monitor assignment every frame (visible as the logged DPI
/// oscillating 96/120 many times a second with the window not actually
/// moving). Both now always agree, derived from the same lookup.
///
/// Falls back to the window's own current `GetDpiForWindow` applied
/// from the origin if no monitor contains the point at all (e.g.
/// transiently during a display reconfiguration).
fn resolve_monitor_scale_and_position(
    window: &tauri::window::Window,
    hwnd: HWND,
    x: f64,
    y: f64,
) -> (f64, i32, i32) {
    let monitors = window.available_monitors().unwrap_or_default();
    for m in &monitors {
        let scale = m.scale_factor();
        let pos = m.position();
        let size = m.size();
        let logical_left = pos.x as f64 / scale;
        let logical_top = pos.y as f64 / scale;
        let logical_right = logical_left + size.width as f64 / scale;
        let logical_bottom = logical_top + size.height as f64 / scale;
        if x >= logical_left && x < logical_right && y >= logical_top && y < logical_bottom {
            return (
                scale,
                (pos.x as f64 + (x - logical_left) * scale).round() as i32,
                (pos.y as f64 + (y - logical_top) * scale).round() as i32,
            );
        }
    }
    let dpi = unsafe { GetDpiForWindow(hwnd) };
    let scale = if dpi == 0 { 1.0 } else { dpi as f64 / 96.0 };
    (scale, (x * scale).round() as i32, (y * scale).round() as i32)
}

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
///
/// Also asks DWM to skip its own window-resize transition animation for
/// this window (`DWMWA_TRANSITIONS_FORCEDISABLED`). Pet windows call
/// `UpdateLayeredWindow` roughly every tick (~30ms), including with a
/// new size on a rescale or a monitor crossing (task 6.5/7.2) -- if DWM
/// tries to animate each of those as a normal window resize, calling it
/// again before the animation settles would mean the pet visibly never
/// finishes "growing into" or "shrinking into" its new size, which
/// would look exactly like the content and window bounds not matching.
pub fn make_layered(window: &tauri::window::Window) {
    let Some(hwnd) = hwnd_of(window) else { return };
    unsafe {
        let current = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED.0 as isize);

        let disable_transitions: i32 = 1;
        let _ = DwmSetWindowAttribute(
            hwnd,
            DWMWA_TRANSITIONS_FORCEDISABLED,
            &disable_transitions as *const i32 as *const core::ffi::c_void,
            size_of::<i32>() as u32,
        );
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
    /// The 1x1 monochrome stub bitmap `CreateCompatibleDC` selects into
    /// a fresh memory DC by default (returned by the first
    /// `SelectObject` call) -- saved so it can be selected back in
    /// before deleting our own bitmap on a resize or drop. Deleting a
    /// GDI object while it's still selected into a DC is undefined
    /// behavior per Microsoft's own docs; this is what left stale or
    /// corrupted content on screen (wrong scale, cropped edges) until
    /// some unrelated event -- e.g. a monitor change -- forced a full
    /// recomposite that happened to paper over it.
    default_bitmap: HGDIOBJ,
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
                if !self.default_bitmap.is_invalid() {
                    let _ = SelectObject(self.mem_dc, self.default_bitmap);
                }
                let _ = DeleteObject(self.bitmap.into());
            }
            if !self.mem_dc.is_invalid() {
                let _ = DeleteDC(self.mem_dc);
            }
        }
    }
}

impl LayeredSurface {
    /// A margin the *window* is rendered larger than the sprite by (on
    /// every side except top/left -- the sprite is pinned to the
    /// window's top-left corner, so `state.x/y` keeps meaning exactly
    /// what it does on every other platform). Real hardware testing
    /// went through several rounds of DPI/monitor/animation fixes that
    /// each proved (via logging) the size and position math was exactly
    /// correct, yet screenshots still showed the sprite cropped by a
    /// hard window edge -- something between "the numbers we compute"
    /// and "what Windows actually shows" doesn't line up by a few
    /// percent, and no fix found the exact mechanism. Rather than keep
    /// chasing an exact match, the window is deliberately given this
    /// much breathing room so a small mismatch no longer crops anything
    /// visible -- the margin itself is fully transparent, so it isn't
    /// visible when there's no mismatch either.
    // Bumped way up (from 1.1) purely as a diagnostic: the 10% margin
    // made no visible difference at all to the reported cropping, which
    // means either the real mismatch is much bigger than 10%, or this
    // isn't actually a size problem. This is deliberately wasteful
    // (3x the canvas area) and not meant to ship -- it's here to find
    // out which of those two is true before spending more effort on
    // either theory.
    const MARGIN_FACTOR: f64 = 3.0;

    /// Returns whether it actually rebuilt the DIB (vs. a same-size
    /// no-op) -- purely so `update` can log the before/after numbers
    /// only when something changes, not every frame.
    fn ensure_size(&mut self, width: u32, height: u32) -> bool {
        if self.width == width && self.height == height && !self.mem_dc.is_invalid() {
            return false;
        }
        unsafe {
            if self.mem_dc.is_invalid() {
                self.mem_dc = CreateCompatibleDC(None);
            }
            if !self.bitmap.is_invalid() {
                // Restore whatever was selected into the DC before our
                // own bitmap so deleting it below is well-defined.
                if !self.default_bitmap.is_invalid() {
                    let _ = SelectObject(self.mem_dc, self.default_bitmap);
                }
                let _ = DeleteObject(self.bitmap.into());
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
                return false;
            };
            let previous = SelectObject(self.mem_dc, bitmap.into());
            if self.default_bitmap.is_invalid() {
                // First-ever selection into this DC: `previous` is the
                // stock bitmap `CreateCompatibleDC` gave it.
                self.default_bitmap = previous;
            }
            self.bitmap = bitmap;
            self.pixels = bits as *mut u8;
            self.width = width;
            self.height = height;
        }
        true
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
    ///
    /// The window itself is sized to `scaled_w/h * MARGIN_FACTOR`
    /// (see that constant's doc) -- the sprite is drawn at its real
    /// size into the top-left of that larger, otherwise fully
    /// transparent canvas.
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

        // Defensive: the process is already declared Per-Monitor-V2 DPI
        // aware (tao does this once at startup), which should cover
        // every thread -- but DPI awareness in Windows also has a
        // *per-thread* override, and if anything on this thread (main,
        // shared with webview/COM machinery) ever resets it, Windows
        // can silently apply its own compatibility bitmap-stretching to
        // this exact UpdateLayeredWindow call regardless of how correct
        // the numbers we pass it are.
        unsafe {
            let _ = SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        }

        let (dpi_scale, phys_x, phys_y) = resolve_monitor_scale_and_position(window, hwnd, x, y);
        let box_w = (scaled_w as f64 * Self::MARGIN_FACTOR).round() as u32;
        let box_h = (scaled_h as f64 * Self::MARGIN_FACTOR).round() as u32;
        let physical_box_w = (box_w as f64 * dpi_scale).round() as u32;
        let physical_box_h = (box_h as f64 * dpi_scale).round() as u32;
        let physical_content_w = (scaled_w as f64 * dpi_scale).round() as u32;
        let physical_content_h = (scaled_h as f64 * dpi_scale).round() as u32;
        if physical_box_w == 0 || physical_box_h == 0 {
            return;
        }

        if self.ensure_size(physical_box_w, physical_box_h) {
            // Windows' own idea of this window's current DPI, for
            // comparison against `scale` (derived independently from
            // the monitor lookup above) -- if these ever disagree,
            // that's Windows applying some compatibility scaling of its
            // own on top of what we're correctly computing.
            let hwnd_dpi = unsafe { GetDpiForWindow(hwnd) };
            log::info!(
                "layered surface resize: scale={dpi_scale} hwnd_dpi={hwnd_dpi} \
                 frame={frame_w}x{frame_h} scaled(logical)={scaled_w}x{scaled_h} \
                 box(physical)={physical_box_w}x{physical_box_h} \
                 content(physical)={physical_content_w}x{physical_content_h} pos=({phys_x}, \
                 {phys_y})"
            );
        }
        if self.pixels.is_null() {
            return;
        }

        let dst = unsafe {
            std::slice::from_raw_parts_mut(
                self.pixels,
                (physical_box_w * physical_box_h * 4) as usize,
            )
        };
        // Fully transparent margin by default; only the top-left
        // content_w x content_h region gets real pixels below. Zeroed
        // unconditionally (not just for the newly-grown area on an
        // `ensure_size` rebuild) since the content region's own size
        // can shrink frame to frame (a smaller cue, a rescale down),
        // which would otherwise leave stale opaque pixels from a
        // previous, larger frame sitting in what's now margin.
        dst.fill(0);
        for dst_y in 0..physical_content_h {
            let src_y = (dst_y * frame_h / physical_content_h).min(frame_h - 1);
            for dst_x in 0..physical_content_w {
                let src_x = (dst_x * frame_w / physical_content_w).min(frame_w - 1);
                let src_off = ((src_y * frame_w + src_x) * 4) as usize;
                let dst_off = ((dst_y * physical_box_w + dst_x) * 4) as usize;
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

        let dst_pos = POINT { x: phys_x, y: phys_y };
        let size = SIZE { cx: physical_box_w as i32, cy: physical_box_h as i32 };
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
