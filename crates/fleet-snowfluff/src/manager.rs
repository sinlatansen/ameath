//! Owns every pet window, the shared GPU context, and the background
//! tick loop that drives motion, drag detection, and rendering (tasks
//! 6.1/6.6/6.7). Multi-instance count is authoritative here; the pure
//! swarm-sizing rule itself lives in `fleet_snowfluff_core::PetSwarm`
//! semantics (clamped 1..=80), enforced when applying an instance-count
//! change.

use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc,
};

use device_query::DeviceState;
use fleet_snowfluff_core::{Bounds, MotionSettings, UiLanguage, VoiceLanguage, WanderStayMode};
use rand::{rngs::StdRng, SeedableRng};

use crate::{
    animation::{load_animation_set, AnimationSet},
    assets::assets_dir,
    gfx::{GpuContext, PetSurface},
    pet::PetWindow,
    voice::VoicePlayer,
};

const MIN_INSTANCES: usize = fleet_snowfluff_core::swarm::MIN_INSTANCES;
const MAX_INSTANCES: usize = fleet_snowfluff_core::swarm::MAX_INSTANCES;

static NEXT_PET_ID: AtomicU64 = AtomicU64::new(0);

fn next_label() -> String { format!("pet-{}", NEXT_PET_ID.fetch_add(1, Ordering::Relaxed)) }

/// Converts a monitor's rect from the physical pixels `Monitor` reports
/// to the logical points `LogicalPosition`/`LogicalSize` (what window
/// placement actually uses) -- getting this wrong is exactly how pets
/// end up spawned off-screen on any HiDPI display, worse with multiple
/// monitors at different scale factors.
fn monitor_logical_bounds(m: &tauri::window::Monitor) -> Bounds {
    let scale = m.scale_factor();
    let pos = m.position();
    let size = m.size();
    let left = pos.x as f64 / scale;
    let top = pos.y as f64 / scale;
    Bounds {
        left,
        top,
        right: left + size.width as f64 / scale,
        bottom: top + size.height as f64 / scale,
    }
}

/// Sums every monitor's bounds into one roaming area (legacy's
/// `total_screen` mode), or confines to a single monitor otherwise:
/// `monitor_index` into `available_monitors()` if it's in range
/// (desktop-integration spec's "confinement to one selected monitor"),
/// falling back to the primary monitor for a negative or out-of-range
/// index (legacy's own default). Falls back to a reasonable default
/// bounds if monitor info is unavailable at all (e.g. running headless).
fn compute_bounds(app: &tauri::AppHandle, total_screen: bool, monitor_index: i64) -> Bounds {
    let fallback = Bounds { left: 0.0, top: 0.0, right: 1920.0, bottom: 1080.0 };

    if total_screen {
        match app.available_monitors() {
            Ok(monitors) if !monitors.is_empty() => {
                let mut left = f64::INFINITY;
                let mut top = f64::INFINITY;
                let mut right = f64::NEG_INFINITY;
                let mut bottom = f64::NEG_INFINITY;
                for m in &monitors {
                    let b = monitor_logical_bounds(m);
                    left = left.min(b.left);
                    top = top.min(b.top);
                    right = right.max(b.right);
                    bottom = bottom.max(b.bottom);
                }
                Bounds { left, top, right, bottom }
            }
            _ => fallback,
        }
    } else {
        let selected = usize::try_from(monitor_index)
            .ok()
            .and_then(|idx| app.available_monitors().ok().and_then(|ms| ms.get(idx).cloned()));
        match selected.or_else(|| app.primary_monitor().ok().flatten()) {
            Some(m) => monitor_logical_bounds(&m),
            None => fallback,
        }
    }
}

pub struct PetManager {
    app: tauri::AppHandle,
    instance: wgpu::Instance,
    gpu: Option<GpuContext>,
    animations: Option<Arc<AnimationSet>>,
    pets: Vec<PetWindow>,
    bounds: Bounds,
    /// Roam across every monitor combined (legacy's `total_screen`), or
    /// stay confined to the primary monitor. Toggling recomputes `bounds`
    /// immediately; in-flight pets pick up the new bounds on their next
    /// tick (existing positions are left as-is, matching legacy, rather
    /// than snapping pets that are now technically out of bounds).
    total_screen: bool,
    /// Which monitor to confine to when `total_screen` is false; an
    /// index into `available_monitors()`, or out of range (default -1)
    /// to mean "the primary monitor".
    monitor_index: i64,
    pub settings: MotionSettings,
    pub scale: f64,
    pub opacity: f32,
    pub paused: bool,
    /// User-requested visibility (tray/quick-menu show/hide, task 12.1),
    /// independent of the mode-2 fullscreen auto-hide -- a pet is only
    /// actually shown when both this is true and it isn't currently
    /// hidden behind a fullscreen app, see `apply_visibility`.
    visible: bool,
    /// Whether paused pets dock to the current foreground window (task
    /// 6.8, D15). Only wired up on macOS so far (7.2/9.2 remain).
    window_snap: bool,
    click_through: bool,
    /// 1 = topmost, 2 = normal + fullscreen-hide, 3 = desktop-only.
    /// Platform layering (tasks 7/8/9) applies the actual OS behavior;
    /// only macOS is wired up so far.
    display_priority: i64,
    rng: StdRng,
    /// `None` when global mouse polling is unavailable -- e.g. on macOS
    /// without Accessibility permission granted. `device_query`'s
    /// constructor panics in that case (inside a callback the OS won't
    /// let unwind past), so it's built behind `catch_unwind` and drag /
    /// follow-mouse are simply disabled rather than crashing the app.
    device_state: Option<DeviceState>,
    drag_owner: Option<usize>,
    was_left_down: bool,
    was_right_down: bool,
    tick_count: u64,
    voice: VoicePlayer,
    ui_language: UiLanguage,
    #[cfg(target_os = "macos")]
    hidden_by_fullscreen: bool,
}

impl PetManager {
    pub fn new(app: tauri::AppHandle, total_screen: bool) -> Self {
        let monitor_index = -1;
        let bounds = compute_bounds(&app, total_screen, monitor_index);
        let device_state = std::panic::catch_unwind(std::panic::AssertUnwindSafe(DeviceState::new))
            .inspect_err(|_| {
                log::warn!(
                    "global mouse polling unavailable (likely missing OS input-monitoring \
                     permission) -- drag and follow-mouse will be disabled this session"
                );
            })
            .ok();
        // Bootstrap value only -- lib.rs's setup overrides it with the
        // real config's voice_language immediately after construction,
        // same pattern as PetManager's other Config::default()-seeded
        // fields.
        let voice = VoicePlayer::new(&assets_dir().join("voice"), VoiceLanguage::default());

        Self {
            app,
            instance: wgpu::Instance::new(&wgpu::InstanceDescriptor::default()),
            gpu: None,
            animations: None,
            pets: Vec::new(),
            bounds,
            total_screen,
            monitor_index,
            settings: MotionSettings {
                follow_mouse: false,
                wander_idle_stay_mode: WanderStayMode::Stationary,
            },
            scale: 1.0,
            opacity: 1.0,
            paused: false,
            visible: true,
            window_snap: true,
            click_through: false,
            display_priority: 1,
            rng: StdRng::from_os_rng(),
            device_state,
            drag_owner: None,
            was_left_down: false,
            was_right_down: false,
            tick_count: 0,
            voice,
            // Full config-file persistence (task 13.2) will let a saved
            // override beat this; until then every launch resolves fresh
            // from the system locale, matching the localization spec's
            // first-run behavior.
            ui_language: fleet_snowfluff_core::detect_ui_language(),
            #[cfg(target_os = "macos")]
            hidden_by_fullscreen: false,
        }
    }

    fn ensure_animations(&mut self) -> Arc<AnimationSet> {
        if self.animations.is_none() {
            self.animations = Some(Arc::new(load_animation_set(&assets_dir().join("gifs"))));
        }
        self.animations.clone().unwrap()
    }

    fn spawn_one(&mut self) {
        let animations = self.ensure_animations();
        let label = next_label();
        log::info!(
            "spawning pet {label} (bounds: {:?}..{:?} .. {:?}..{:?})",
            self.bounds.left,
            self.bounds.right,
            self.bounds.top,
            self.bounds.bottom
        );

        let window = tauri::window::WindowBuilder::new(&self.app, &label)
            .title("Fleet Snowfluff")
            .decorations(false)
            .transparent(true)
            .always_on_top(true)
            .resizable(false)
            .skip_taskbar(true)
            .inner_size(
                animations.move_right.width as f64 * self.scale,
                animations.move_right.height as f64 * self.scale,
            )
            .position(-10_000.0, -10_000.0)
            .build()
            .expect("create pet window");

        let raw_surface =
            self.instance.create_surface(window.clone()).expect("create wgpu surface for pet");

        if self.gpu.is_none() {
            self.gpu = Some(GpuContext::new(&self.instance, &raw_surface));
        }
        let gpu = self.gpu.as_ref().unwrap();

        let w = (animations.move_right.width as f64 * self.scale).round() as u32;
        let h = (animations.move_right.height as f64 * self.scale).round() as u32;
        let surface = PetSurface::new(gpu, raw_surface, w, h);

        let pet = PetWindow::new(
            window,
            gpu,
            surface,
            animations,
            self.bounds,
            self.scale,
            self.opacity,
            &mut self.rng,
        );
        log::info!("spawned {label} at ({:.1}, {:.1})", pet.state.x, pet.state.y);
        pet.apply_display_priority(self.display_priority);
        pet.window.set_ignore_cursor_events(self.click_through).ok();
        self.pets.push(pet);
        self.apply_visibility();
    }

    pub fn set_instance_count(&mut self, count: usize) {
        let count = count.clamp(MIN_INSTANCES, MAX_INSTANCES);
        log::info!("set_instance_count: {} -> {count}", self.pets.len());
        while self.pets.len() < count {
            self.spawn_one();
        }
        log::info!("set_instance_count done: {} pets", self.pets.len());
        while self.pets.len() > count {
            if let Some(pet) = self.pets.pop() {
                pet.window.close().ok();
            }
        }
    }

    pub fn total_screen(&self) -> bool { self.total_screen }

    /// Switches between roaming all monitors and confining to a single
    /// one (desktop-integration spec: "Multi-monitor placement").
    pub fn set_total_screen(&mut self, total_screen: bool) {
        self.total_screen = total_screen;
        self.recompute_bounds();
    }

    pub fn monitor_index(&self) -> i64 { self.monitor_index }

    /// Which monitor to confine to when not roaming all screens; only
    /// takes effect once `total_screen` is false.
    pub fn set_monitor_index(&mut self, monitor_index: i64) {
        self.monitor_index = monitor_index;
        self.recompute_bounds();
    }

    fn recompute_bounds(&mut self) {
        self.bounds = compute_bounds(&self.app, self.total_screen, self.monitor_index);
        log::info!(
            "bounds -> {:?}..{:?} x {:?}..{:?} (total_screen: {}, monitor_index: {})",
            self.bounds.left,
            self.bounds.right,
            self.bounds.top,
            self.bounds.bottom,
            self.total_screen,
            self.monitor_index
        );
    }

    pub fn set_scale(&mut self, scale: f64) {
        self.scale = scale;
        if let Some(gpu) = &self.gpu {
            for pet in &mut self.pets {
                pet.set_scale(gpu, scale);
            }
        }
    }

    pub fn set_opacity(&mut self, opacity: f32) {
        self.opacity = opacity;
        if let Some(gpu) = &self.gpu {
            for pet in &mut self.pets {
                pet.set_opacity(gpu, opacity);
            }
        }
    }

    pub fn set_paused(&mut self, paused: bool) {
        self.paused = paused;
        for pet in &mut self.pets {
            pet.paused = paused;
        }
    }

    pub fn visible(&self) -> bool { self.visible }

    /// User-requested show/hide (tray/quick-menu, task 12.1). Combined
    /// with the mode-2 fullscreen auto-hide via `apply_visibility` --
    /// either one hiding the pets is enough to hide them.
    pub fn set_visible(&mut self, visible: bool) {
        self.visible = visible;
        self.apply_visibility();
    }

    fn apply_visibility(&self) {
        #[cfg(target_os = "macos")]
        let effective = self.visible && !self.hidden_by_fullscreen;
        #[cfg(not(target_os = "macos"))]
        let effective = self.visible;
        for pet in &self.pets {
            pet.set_visible(effective);
        }
    }

    pub fn window_snap(&self) -> bool { self.window_snap }

    pub fn set_window_snap(&mut self, enable: bool) { self.window_snap = enable; }

    pub fn click_through(&self) -> bool { self.click_through }

    /// Toggles real OS-level click-through (`set_ignore_cursor_events`)
    /// on every pet, not just our own drag-detection gate (task 7/8/9's
    /// "click-through" requirement -- previously this field only
    /// suppressed drag start, it never told the OS to pass clicks
    /// through).
    pub fn set_click_through(&mut self, enable: bool) {
        self.click_through = enable;
        for pet in &self.pets {
            pet.window.set_ignore_cursor_events(enable).ok();
        }
    }

    pub fn display_priority(&self) -> i64 { self.display_priority }

    /// Applies a display-priority mode (1 = topmost, 2 = normal +
    /// fullscreen-hide, 3 = desktop-only) to every pet immediately.
    /// Mode 2's continuous fullscreen monitoring happens in `tick`.
    pub fn set_display_priority(&mut self, mode: i64) {
        self.display_priority = mode;
        for pet in &self.pets {
            pet.apply_display_priority(mode);
        }
    }

    pub fn ui_language(&self) -> UiLanguage { self.ui_language }

    pub fn set_ui_language(&mut self, language: UiLanguage) { self.ui_language = language; }

    /// The active UI language's locale dictionary as raw JSON, for the
    /// settings webview to `JSON.parse` itself (task 11.2) -- the
    /// dictionary is the single source of truth for both Rust and the
    /// webview, so this hands over the authored file verbatim rather
    /// than re-serializing a parsed form.
    pub fn locale_dictionary_json(&self) -> &'static str {
        fleet_snowfluff_core::dictionary_json(self.ui_language)
    }

    pub fn set_voice_enabled(&mut self, enabled: bool) { self.voice.set_enabled(enabled); }

    pub fn set_voice_volume_percent(&mut self, percent: i64) {
        self.voice.set_volume_percent(percent);
    }

    pub fn set_voice_language(&mut self, language: VoiceLanguage) {
        self.voice.set_language(language);
    }

    pub fn voice_language(&self) -> VoiceLanguage { self.voice.active_language() }

    pub fn voice_languages_with_clips(&self) -> &[VoiceLanguage] {
        self.voice.languages_with_clips()
    }

    /// One iteration of the background tick: polls global mouse state
    /// once (position + left-button) for both follow-mouse targeting and
    /// drag detection (task 6.6 -- Tauri's windowless Window has no
    /// click events, see design.md), advances every pet, and renders.
    /// Returns the pet window a quick menu should open on, if any --
    /// the caller must show it only *after* releasing the `PetManager`
    /// lock this method runs under (see the doc comment at the
    /// right-click detection site below for why).
    pub fn tick(&mut self, dt_ms: i64) -> Option<tauri::window::Window> {
        let gpu = self.gpu.as_ref()?;

        let (cursor, left_down, right_down) = match &self.device_state {
            Some(ds) => {
                let mouse_state = ds.query_pointer();
                let cursor = (mouse_state.coords.0 as f64, mouse_state.coords.1 as f64);
                // device_query's button_pressed is 1-indexed (button
                // numbers, not array positions) -- index 0 is documented
                // as always false/meaningless; index 1 is the left
                // button, index 2 is the right button.
                let left_down = mouse_state.button_pressed.get(1).copied().unwrap_or(false);
                let right_down = mouse_state.button_pressed.get(2).copied().unwrap_or(false);
                (cursor, left_down, right_down)
            }
            // No mouse polling available: pets still move, just never
            // drag, follow the cursor, or open the quick menu.
            None => ((0.0, 0.0), false, false),
        };
        let left_pressed_this_tick = left_down && !self.was_left_down;
        let left_released_this_tick = !left_down && self.was_left_down;
        self.was_left_down = left_down;
        let right_pressed_this_tick = right_down && !self.was_right_down;
        self.was_right_down = right_down;

        // Set when a right-click lands on a pet this tick; returned to
        // the caller so it can pop the menu up only after releasing the
        // `Mutex<PetManager>` lock `tick` runs under -- `Menu::popup`
        // reads current state (paused/visible/follow/click-through) to
        // build its labels, and doing that from in here, while the lock
        // this same method is called under is still held, would deadlock
        // a non-reentrant `std::sync::Mutex` against itself.
        let mut pending_quick_menu = None;

        if self.device_state.is_some() && !self.click_through {
            if left_pressed_this_tick && self.drag_owner.is_none() {
                if let Some(idx) = self.pets.iter().position(|p| p.bounds_contains(cursor)) {
                    self.pets[idx].start_drag(cursor);
                    self.drag_owner = Some(idx);
                    self.voice.play_random();
                }
            } else if left_released_this_tick {
                if let Some(idx) = self.drag_owner.take() {
                    if let Some(pet) = self.pets.get_mut(idx) {
                        pet.stop_drag();
                    }
                }
            }

            // Quick context menu (task 12.2): windowless pet windows get
            // no native right-click event, so this rides the same global
            // mouse poll as drag detection.
            if right_pressed_this_tick {
                if let Some(idx) = self.pets.iter().position(|p| p.bounds_contains(cursor)) {
                    pending_quick_menu = Some(self.pets[idx].window.clone());
                }
            }
        }

        let follow_target = if self.settings.follow_mouse && self.device_state.is_some() {
            Some(cursor)
        } else {
            None
        };

        self.tick_count += 1;
        let log_positions = self.tick_count.is_multiple_of(33); // ~once/second

        // Mode 2's fullscreen-hide needs OS window introspection, which
        // isn't worth doing every ~30ms tick; check on the same ~1s
        // cadence as the debug position log (legacy polls every 500ms).
        #[cfg(target_os = "macos")]
        if self.display_priority == 2 && log_positions {
            let is_fullscreen = crate::platform::macos::foreground_window()
                .map(|w| w.covers(self.bounds))
                .unwrap_or(false);
            if is_fullscreen != self.hidden_by_fullscreen {
                self.hidden_by_fullscreen = is_fullscreen;
                self.apply_visibility();
            }
        }

        // Pause-mode window-snap docking (task 6.8): re-querying the
        // foreground window is an OS call, so it rides the same ~1s
        // throttle as the fullscreen check above rather than running
        // every ~30ms tick. Only macOS has a foreground-window query
        // wired up so far (7.2/9.2 will add the others at this same
        // call site).
        #[cfg(target_os = "macos")]
        let dock_window = if self.window_snap && log_positions {
            crate::platform::macos::foreground_window().map(|w| w.rect)
        } else {
            None
        };

        for (idx, pet) in self.pets.iter_mut().enumerate() {
            if Some(idx) == self.drag_owner {
                pet.drag_to(cursor);
                pet.apply_drag_position(gpu);
            } else {
                pet.tick(gpu, self.bounds, follow_target, self.settings, dt_ms, &mut self.rng);
                #[cfg(target_os = "macos")]
                if self.window_snap && log_positions && pet.paused {
                    pet.apply_dock(gpu, self.bounds, dock_window);
                }
            }
            if log_positions {
                log::debug!("pet {idx}: ({:.1}, {:.1})", pet.state.x, pet.state.y);
            }
            pet.render(gpu);
        }

        pending_quick_menu
    }

    pub fn len(&self) -> usize { self.pets.len() }

    pub fn is_empty(&self) -> bool { self.pets.is_empty() }
}
