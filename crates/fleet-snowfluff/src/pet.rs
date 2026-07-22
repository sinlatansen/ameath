//! A single pet: its window, GPU surface, and the display-side state
//! (which animation cue is showing, frame timing) layered on top of the
//! pure `fleet_snowfluff_core::PetState`. Ties the core tick, the
//! animation set, and the wgpu surface together (tasks 6.1/6.3/6.4/6.5).

use std::{sync::Arc, time::Instant};

use fleet_snowfluff_core::{
    compute_dock_position, Bounds, ForeignWindowRect, MotionSettings, PauseAnimEvent,
    PauseAnimationScheduler, PetSize, PetState, TickInput,
};
use rand::Rng;

use crate::{
    animation::{AnimationCue, AnimationSet},
    gfx::{GpuContext, PetSurface},
};

pub struct PetWindow {
    pub window: tauri::window::Window,
    surface: PetSurface,
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
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        window: tauri::window::Window,
        gpu: &GpuContext,
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
            pause_scheduler: PauseAnimationScheduler::new(rng),
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

    pub fn set_scale(&mut self, gpu: &GpuContext, scale: f64) {
        self.scale = scale;
        self.apply_window_size(gpu);
    }

    pub fn set_opacity(&mut self, gpu: &GpuContext, opacity: f32) {
        self.opacity = opacity;
        self.surface.set_opacity(gpu, opacity);
    }

    /// Applies a display-priority mode: 1 = topmost, 2 = normal (with
    /// fullscreen-hide handled separately by the manager's periodic
    /// check, since it needs OS window introspection), 3 = desktop-only.
    /// macOS (8.1/8.3) and Windows (7.1/7.3) are wired up; Linux (group
    /// 9) falls back to plain topmost until it lands.
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
        #[cfg(not(any(target_os = "macos", target_os = "windows")))]
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
    pub fn apply_dock(
        &mut self,
        gpu: &GpuContext,
        bounds: Bounds,
        window: Option<ForeignWindowRect>,
    ) {
        if !self.paused {
            return;
        }
        let size =
            self.size_for(self.animations.move_right.width, self.animations.move_right.height);
        match compute_dock_position(window, bounds, size) {
            Some((x, y)) => {
                self.docked = true;
                self.apply_window_size(gpu);
                self.window
                    .set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y)))
                    .ok();
            }
            None if self.docked => {
                self.docked = false;
                self.apply_window_size(gpu);
                let (x, y) = (self.state.x.round(), self.state.y.round());
                self.window
                    .set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y)))
                    .ok();
            }
            None => {}
        }
    }

    fn size_for(&self, native_w: u32, native_h: u32) -> PetSize {
        PetSize { w: native_w as f64 * self.scale, h: native_h as f64 * self.scale }
    }

    fn apply_window_size(&mut self, gpu: &GpuContext) {
        let clip = self.animations.clip_for(self.cue, self.state.moving_right);
        let size = self.size_for(clip.width, clip.height);
        let (w, h) = (size.w.round() as u32, size.h.round() as u32);
        if (w, h) != self.current_window_size {
            self.window
                .set_size(tauri::Size::Logical(tauri::LogicalSize::new(size.w, size.h)))
                .ok();
            self.surface.resize(gpu, w, h);
            self.current_window_size = (w, h);
        }
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
        gpu: &GpuContext,
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
            match self.pause_scheduler.tick(dt_ms, rng) {
                PauseAnimEvent::PlayRandomAnimation => {
                    self.screen_variant = rng.random_range(0..self.animations.screen.len());
                    self.set_cue(AnimationCue::Screen(self.screen_variant));
                }
                PauseAnimEvent::ReturnToIdle => {
                    self.set_cue(AnimationCue::Paused);
                }
                PauseAnimEvent::None => {}
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
        let (x, y) = (self.state.x.round(), self.state.y.round());
        self.window.set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y))).ok();
    }

    /// Applies the current drag position to the window (called every
    /// tick while dragging, separate from `tick` since dragging skips
    /// the core state machine entirely).
    pub fn apply_drag_position(&mut self, gpu: &GpuContext) {
        self.apply_window_size(gpu);
        let (x, y) = (self.state.x.round(), self.state.y.round());
        self.window.set_position(tauri::Position::Logical(tauri::LogicalPosition::new(x, y))).ok();
    }

    /// Advances the animation frame if its delay has elapsed and draws
    /// the current frame.
    pub fn render(&mut self, gpu: &GpuContext) {
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
        self.surface.render(gpu, frame, clip.width, clip.height);
    }

    pub fn bounds_contains(&self, point: (f64, f64)) -> bool {
        let (w, h) = self.current_window_size;
        point.0 >= self.state.x
            && point.0 <= self.state.x + w as f64
            && point.1 >= self.state.y
            && point.1 <= self.state.y + h as f64
    }
}
