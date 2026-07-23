//! A single pet: its window, GPU surface (or, on Windows, GDI layered-
//! window surface -- see `platform/windows.rs`'s module doc for why
//! these two platforms render completely differently), and the
//! display-side state (which animation cue is showing, frame timing)
//! layered on top of the pure `fleet_snowfluff_core::PetState`. Ties
//! the core tick, the animation set, and the rendering backend together
//! (tasks 6.1/6.3/6.4/6.5).

use std::{sync::Arc, time::Instant};

use fleet_snowfluff_core::{
    compute_dock_position, Bounds, ForeignWindowRect, MotionSettings, PauseAnimEvent,
    PauseAnimationScheduler, PetSize, PetState, TickInput,
};
use rand::Rng;

use crate::animation::{AnimationCue, AnimationSet};
#[cfg(not(target_os = "windows"))]
use crate::gfx::{GpuContext, PetSurface};

/// The rendering backend's shared context, threaded through the same
/// call sites on every platform (`PetManager::tick`, `PetWindow::
/// render`, etc.) so those don't need platform-specific branches of
/// their own. On Windows this is a meaningless placeholder -- there is
/// no shared GPU context at all, since pet windows render via GDI
/// (`platform::windows::LayeredSurface`) instead of a wgpu swapchain.
#[cfg(not(target_os = "windows"))]
pub type Gpu = GpuContext;
#[cfg(target_os = "windows")]
pub type Gpu = ();

pub struct PetWindow {
    pub window: tauri::window::Window,
    #[cfg(not(target_os = "windows"))]
    surface: PetSurface,
    #[cfg(target_os = "windows")]
    layered: crate::platform::windows::LayeredSurface,
    /// Overrides the position `render()` draws at, while pause-mode
    /// window-snap docking (task 6.8) is active -- `state.x/y` stays
    /// the pre-dock resting position to restore on undock, unchanged
    /// by docking itself. Only needed on Windows: elsewhere, docking
    /// moves the *window* directly via `window.set_position()` and
    /// `render()` never needs to know about position at all.
    #[cfg(target_os = "windows")]
    dock_position: Option<(f64, f64)>,
    pub state: PetState,
    animations: Arc<AnimationSet>,
    pause_scheduler: PauseAnimationScheduler,
    pub paused: bool,
    /// Whether this pet is currently snapped to a foreground window
    /// (task 6.8). Tracked so undocking can restore `state.x/y`, which
    /// is never written while paused otherwise -- it's already the
    /// pre-dock resting position, no separate save needed.
    docked: bool,
    pub dragging: bool,
    drag_offset: (f64, f64),
    cue: AnimationCue,
    idle_variant: usize,
    screen_variant: usize,
    frame_index: usize,
    frame_started_at: Instant,
    frame_frozen: bool,
    scale: f64,
    opacity: f32,
    current_window_size: (u32, u32),
}

impl PetWindow {
    /// `surface` must already be configured (via `PetSurface::new`) for
    /// `window` -- surface creation is the manager's job since bootstrapping
    /// the shared `GpuContext` needs the very first pet's raw surface to
    /// exist before `GpuContext::new` can run. All params are required
    /// (no sensible defaults for a freshly-spawned pet), so a builder
    /// would add ceremony without adding clarity.
    #[cfg(not(target_os = "windows"))]
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        window: tauri::window::Window,
        gpu: &Gpu,
        surface: PetSurface,
        animations: Arc<AnimationSet>,
        bounds: Bounds,
        scale: f64,
        opacity: f32,
        rng: &mut impl Rng,
    ) -> Self {
        let size = PetSize {
            w: animations.move_right.width as f64 * scale,
            h: animations.move_right.height as f64 * scale,
        };
        let state = PetState::spawn(bounds, size, rng);
        surface.set_opacity(gpu, opacity);

        window
            .set_position(tauri::Position::Logical(tauri::LogicalPosition::new(state.x, state.y)))
            .ok();

        Self {
            window,
            surface,
            state,
            animations,
            pause_scheduler: PauseAnimationScheduler::new(),
            paused: false,
            docked: false,
            dragging: false,
            drag_offset: (0.0, 0.0),
            cue: AnimationCue::Move,
            idle_variant: 0,
            screen_variant: 0,
            frame_index: 0,
            frame_started_at: Instant::now(),
            frame_frozen: false,
            scale,
            opacity,
            current_window_size: (size.w as u32, size.h as u32),
        }
    }

    /// No `gpu`/`surface` params here (unlike the other platforms'
    /// `new`) -- `LayeredSurface` has no shared bootstrap dependency at
    /// all, it lazily creates its DIB section on the first `render()`
    /// call. `window` must not have been built with `.transparent(true)`
    /// (see `platform::windows`'s module doc); `make_layered` sets the
    /// one style bit it actually needs instead.
    #[cfg(target_os = "windows")]
    pub fn new(
        window: tauri::window::Window,
        animations: Arc<AnimationSet>,
        bounds: Bounds,
        scale: f64,
        opacity: f32,
        rng: &mut impl Rng,
    ) -> Self {
        let size = PetSize {
            w: animations.move_right.width as f64 * scale,
            h: animations.move_right.height as f64 * scale,
        };
        let state = PetState::spawn(bounds, size, rng);
        crate::platform::windows::make_layered(&window);

        Self {
            window,
            layered: crate::platform::windows::LayeredSurface::default(),
            dock_position: None,
            state,
            animations,
            pause_scheduler: PauseAnimationScheduler::new(),
            paused: false,
            docked: false,
            dragging: false,
            drag_offset: (0.0, 0.0),
            cue: AnimationCue::Move,
            idle_variant: 0,
            screen_variant: 0,
            frame_index: 0,
            frame_started_at: Instant::now(),
            frame_frozen: false,
            scale,
            opacity,
            current_window_size: (size.w as u32, size.h as u32),
        }
    }

    pub fn set_scale(&mut self, gpu: &Gpu, scale: f64) {
        self.scale = scale;
        self.apply_window_size(gpu);
    }

    pub fn set_opacity(&mut self, gpu: &Gpu, opacity: f32) {
        self.opacity = opacity;
        #[cfg(not(target_os = "windows"))]
        self.surface.set_opacity(gpu, opacity);
        #[cfg(target_os = "windows")]
        let _ = gpu;
    }

    /// Applies a display-priority mode: 1 = topmost, 2 = normal (with
    /// fullscreen-hide handled separately by the manager's periodic
    /// check, since it needs OS window introspection), 3 = desktop-only.
    /// macOS (8.1/8.3), Windows (7.1/7.3), and Linux (9.1/9.3) are all
    /// wired up.
    pub fn apply_display_priority(&self, mode: i64) {
        #[cfg(target_os = "macos")]
        {
            if mode == 3 {
                crate::platform::macos::set_desktop_level(&self.window);
                self.window.set_always_on_top(false).ok();
            } else {
                crate::platform::macos::set_normal_level(&self.window);
                self.window.set_always_on_top(true).ok();
            }
        }
        #[cfg(target_os = "windows")]
        {
            if mode == 3 {
                crate::platform::windows::set_desktop_level(&self.window);
                self.window.set_always_on_top(false).ok();
            } else {
                crate::platform::windows::set_normal_level(&self.window);
                self.window.set_always_on_top(true).ok();
            }
        }
        #[cfg(target_os = "linux")]
        {
            if mode == 3 {
                crate::platform::linux::set_desktop_level(&self.window);
                self.window.set_always_on_top(false).ok();
            } else {
                crate::platform::linux::set_normal_level(&self.window);
                self.window.set_always_on_top(true).ok();
            }
        }
        #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
        {
            let _ = mode;
            self.window.set_always_on_top(true).ok();
        }
    }

    pub fn set_visible(&self, visible: bool) {
        if visible {
            self.window.show().ok();
        } else {
            self.window.hide().ok();
        }
    }

    /// Applies pause-mode window-snap docking (task 6.8): docks to the
    /// top-right corner of `window` if it's eligible and the resulting
    /// position fits on screen (`compute_dock_position`), otherwise
    /// releases back to the pre-dock resting position (`state.x/y`,
    /// which docking itself never touches). No-op while not paused.
    /// The caller (manager) is responsible for throttling how often
    /// `window` is refreshed, since producing it is an OS query.
    pub fn apply_dock(&mut self, gpu: &Gpu, bounds: Bounds, window: Option<ForeignWindowRect>) {
        if !self.paused {
            return;
        }
        let size =
            self.size_for(self.animations.move_right.width, self.animations.move_right.height);
        match compute_dock_position(window, bounds, size) {
            Some((x, y)) => {
                self.docked = true;
                self.apply_window_size(gpu);
                #[cfg(not(target_os = "windows"))]
                self.window
                    .set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y)))
                    .ok();
                #[cfg(target_os = "windows")]
                {
                    self.dock_position = Some((x, y));
                }
            }
            None if self.docked => {
                self.docked = false;
                self.apply_window_size(gpu);
                #[cfg(not(target_os = "windows"))]
                {
                    let (x, y) = (self.state.x.round(), self.state.y.round());
                    self.window
                        .set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y)))
                        .ok();
                }
                #[cfg(target_os = "windows")]
                {
                    self.dock_position = None;
                }
            }
            None => {}
        }
    }

    fn size_for(&self, native_w: u32, native_h: u32) -> PetSize {
        PetSize { w: native_w as f64 * self.scale, h: native_h as f64 * self.scale }
    }

    /// Reasserts the window's logical size every tick (cheap: just an
    /// IPC message, not a GPU op) rather than only when our own
    /// `current_window_size` cache disagrees -- on Windows, crossing a
    /// monitor boundary mid-drag can trigger an out-of-band resize (the
    /// OS's own DPI-change handling) that our cache has no way to know
    /// about, so it silently stops correcting a size Windows itself
    /// already corrupted (reported as the window shrinking, then
    /// eventually crashing, specifically while dragging between
    /// differently-scaled monitors). `surface.resize` (an actual GPU
    /// reconfiguration) stays gated on the cache, since that part *is*
    /// only ever wrong when our own intended size changes.
    ///
    /// On Windows there's no separate `set_size` call at all: size,
    /// position, and content all get applied together, atomically, by
    /// `render()`'s `UpdateLayeredWindow` call -- only the
    /// `current_window_size` bookkeeping (used by `bounds_contains` on
    /// every platform) happens here.
    fn apply_window_size(&mut self, gpu: &Gpu) {
        let clip = self.animations.clip_for(self.cue, self.state.moving_right);
        let size = self.size_for(clip.width, clip.height);
        let (w, h) = (size.w.round() as u32, size.h.round() as u32);
        #[cfg(not(target_os = "windows"))]
        {
            self.window
                .set_size(tauri::Size::Logical(tauri::LogicalSize::new(size.w, size.h)))
                .ok();
            if (w, h) != self.current_window_size {
                self.surface.resize(gpu, w, h);
            }
        }
        #[cfg(target_os = "windows")]
        let _ = gpu;
        self.current_window_size = (w, h);
    }

    /// Starts a drag: `cursor` is the global cursor position at press time.
    pub fn start_drag(&mut self, cursor: (f64, f64)) {
        self.dragging = true;
        self.drag_offset = (cursor.0 - self.state.x, cursor.1 - self.state.y);
        self.set_cue(AnimationCue::Drag);
    }

    pub fn drag_to(&mut self, cursor: (f64, f64)) {
        self.state.x = cursor.0 - self.drag_offset.0;
        self.state.y = cursor.1 - self.drag_offset.1;
    }

    pub fn stop_drag(&mut self) {
        self.dragging = false;
        self.set_cue(AnimationCue::Move);
    }

    fn set_cue(&mut self, cue: AnimationCue) {
        if self.cue != cue {
            self.cue = cue;
            self.frame_index = 0;
            self.frame_started_at = Instant::now();
        }
    }

    /// Advances motion/pause state by one tick and updates the window
    /// position/size. Does not render -- call `render` separately so
    /// frame pacing (per-clip delay) can be decoupled from tick pacing.
    pub fn tick(
        &mut self,
        gpu: &Gpu,
        bounds: Bounds,
        mouse: Option<(f64, f64)>,
        settings: MotionSettings,
        dt_ms: i64,
        rng: &mut impl Rng,
    ) {
        if self.dragging {
            return;
        }

        if self.paused {
            // `frame_frozen` otherwise carries over whatever it was set
            // to by the last non-paused tick (true whenever the pet
            // happened to be idle-and-still, e.g. via
            // `!is_moving && !is_idle_playing` below) -- nothing else
            // ever clears it, so a pet that paused while still would
            // stay frozen on frame 0 of the paused/screen cue forever,
            // reported as "the gif does not change" while docked.
            self.frame_frozen = false;
            if self.pause_scheduler.tick(dt_ms, rng) == PauseAnimEvent::PlayRandomAnimation {
                let count = self.animations.screen.len();
                self.screen_variant = if count > 1 {
                    let next = rng.random_range(0..count - 1);
                    if next >= self.screen_variant {
                        next + 1
                    } else {
                        next
                    }
                } else {
                    0
                };
                self.set_cue(AnimationCue::Screen(self.screen_variant));
            }
            self.apply_window_size(gpu);
            return;
        }

        let size =
            self.size_for(self.animations.move_right.width, self.animations.move_right.height);
        let input = TickInput { bounds, size, mouse, settings };
        let events = self.state.tick(&input, rng);

        if events.started_idle {
            self.idle_variant = rng.random_range(0..self.animations.idle.len());
        }

        self.frame_frozen = !self.state.is_moving && !self.state.is_idle_playing;
        let cue = if self.state.is_moving || self.state.is_idle_playing {
            if self.state.is_moving && !self.state.is_idle_playing {
                AnimationCue::Move
            } else {
                AnimationCue::Idle(self.idle_variant)
            }
        } else {
            AnimationCue::Idle(self.idle_variant)
        };
        self.set_cue(cue);

        self.apply_window_size(gpu);
        #[cfg(not(target_os = "windows"))]
        {
            let (x, y) = (self.state.x.round(), self.state.y.round());
            self.window
                .set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y)))
                .ok();
        }
    }

    /// Applies the current drag position to the window (called every
    /// tick while dragging, separate from `tick` since dragging skips
    /// the core state machine entirely).
    pub fn apply_drag_position(&mut self, gpu: &Gpu) {
        self.apply_window_size(gpu);
        #[cfg(not(target_os = "windows"))]
        {
            let (x, y) = (self.state.x.round(), self.state.y.round());
            self.window
                .set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y)))
                .ok();
        }
    }

    /// Advances the animation frame if its delay has elapsed and draws
    /// the current frame.
    pub fn render(&mut self, gpu: &Gpu) {
        let clip = self.animations.clip_for(self.cue, self.state.moving_right);
        if clip.frames.is_empty() {
            return;
        }
        if !self.frame_frozen {
            let delay = clip.frames[self.frame_index.min(clip.frames.len() - 1)].delay;
            if self.frame_started_at.elapsed() >= delay {
                self.frame_index = (self.frame_index + 1) % clip.frames.len();
                self.frame_started_at = Instant::now();
            }
        }
        let frame = &clip.frames[self.frame_index.min(clip.frames.len() - 1)];
        #[cfg(not(target_os = "windows"))]
        self.surface.render(gpu, frame, clip.width, clip.height);
        #[cfg(target_os = "windows")]
        {
            let _ = gpu;
            let (x, y) = self.dock_position.unwrap_or((self.state.x, self.state.y));
            let (scaled_w, scaled_h) = self.current_window_size;
            self.layered.update(
                &self.window,
                &frame.rgba,
                clip.width,
                clip.height,
                scaled_w,
                scaled_h,
                x,
                y,
                self.opacity,
            );
        }
    }

    pub fn bounds_contains(&self, point: (f64, f64)) -> bool {
        let (w, h) = self.current_window_size;
        point.0 >= self.state.x
            && point.0 <= self.state.x + w as f64
            && point.1 >= self.state.y
            && point.1 <= self.state.y + h as f64
    }
}
