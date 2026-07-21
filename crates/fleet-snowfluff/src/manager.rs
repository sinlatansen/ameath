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
use fleet_snowfluff_core::{Bounds, MotionSettings, WanderStayMode};
use rand::{rngs::StdRng, SeedableRng};

use crate::{
    animation::{load_animation_set, AnimationSet},
    assets::assets_dir,
    gfx::{GpuContext, PetSurface},
    pet::PetWindow,
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
/// `total_screen` mode), or returns just the primary monitor's bounds
/// otherwise. Falls back to a reasonable default if monitor info is
/// unavailable (e.g. running headless).
fn compute_bounds(app: &tauri::AppHandle, total_screen: bool) -> Bounds {
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
        match app.primary_monitor() {
            Ok(Some(m)) => monitor_logical_bounds(&m),
            _ => fallback,
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
    pub settings: MotionSettings,
    pub scale: f64,
    pub opacity: f32,
    pub paused: bool,
    pub click_through: bool,
    rng: StdRng,
    /// `None` when global mouse polling is unavailable -- e.g. on macOS
    /// without Accessibility permission granted. `device_query`'s
    /// constructor panics in that case (inside a callback the OS won't
    /// let unwind past), so it's built behind `catch_unwind` and drag /
    /// follow-mouse are simply disabled rather than crashing the app.
    device_state: Option<DeviceState>,
    drag_owner: Option<usize>,
    was_left_down: bool,
    tick_count: u64,
}

impl PetManager {
    pub fn new(app: tauri::AppHandle, total_screen: bool) -> Self {
        let bounds = compute_bounds(&app, total_screen);
        let device_state = std::panic::catch_unwind(std::panic::AssertUnwindSafe(DeviceState::new))
            .inspect_err(|_| {
                log::warn!(
                    "global mouse polling unavailable (likely missing OS input-monitoring \
                     permission) -- drag and follow-mouse will be disabled this session"
                );
            })
            .ok();

        Self {
            app,
            instance: wgpu::Instance::new(&wgpu::InstanceDescriptor::default()),
            gpu: None,
            animations: None,
            pets: Vec::new(),
            bounds,
            total_screen,
            settings: MotionSettings {
                follow_mouse: false,
                wander_idle_stay_mode: WanderStayMode::Stationary,
            },
            scale: 1.0,
            opacity: 1.0,
            paused: false,
            click_through: false,
            rng: StdRng::from_os_rng(),
            device_state,
            drag_owner: None,
            was_left_down: false,
            tick_count: 0,
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
        self.pets.push(pet);
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

    /// Switches between roaming all monitors and confining to the
    /// primary one (desktop-integration spec: "Multi-monitor placement").
    pub fn set_total_screen(&mut self, total_screen: bool) {
        self.total_screen = total_screen;
        self.bounds = compute_bounds(&self.app, total_screen);
        log::info!(
            "total_screen -> {total_screen}, bounds: {:?}..{:?} x {:?}..{:?}",
            self.bounds.left,
            self.bounds.right,
            self.bounds.top,
            self.bounds.bottom
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

    /// One iteration of the background tick: polls global mouse state
    /// once (position + left-button) for both follow-mouse targeting and
    /// drag detection (task 6.6 -- Tauri's windowless Window has no
    /// click events, see design.md), advances every pet, and renders.
    pub fn tick(&mut self, dt_ms: i64) {
        let Some(gpu) = self.gpu.as_ref() else { return };

        let (cursor, left_down) = match &self.device_state {
            Some(ds) => {
                let mouse_state = ds.query_pointer();
                let cursor = (mouse_state.coords.0 as f64, mouse_state.coords.1 as f64);
                // device_query's button_pressed is 1-indexed (button
                // numbers, not array positions) -- index 0 is documented
                // as always false/meaningless; index 1 is the left button.
                let left_down = mouse_state.button_pressed.get(1).copied().unwrap_or(false);
                (cursor, left_down)
            }
            // No mouse polling available: pets still move, just never
            // drag or follow the cursor.
            None => ((0.0, 0.0), false),
        };
        let left_pressed_this_tick = left_down && !self.was_left_down;
        let left_released_this_tick = !left_down && self.was_left_down;
        self.was_left_down = left_down;

        if self.device_state.is_some() && !self.click_through {
            if left_pressed_this_tick && self.drag_owner.is_none() {
                if let Some(idx) = self.pets.iter().position(|p| p.bounds_contains(cursor)) {
                    self.pets[idx].start_drag(cursor);
                    self.drag_owner = Some(idx);
                }
            } else if left_released_this_tick {
                if let Some(idx) = self.drag_owner.take() {
                    if let Some(pet) = self.pets.get_mut(idx) {
                        pet.stop_drag();
                    }
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

        for (idx, pet) in self.pets.iter_mut().enumerate() {
            if Some(idx) == self.drag_owner {
                pet.drag_to(cursor);
                pet.apply_drag_position(gpu);
            } else {
                pet.tick(gpu, self.bounds, follow_target, self.settings, dt_ms, &mut self.rng);
            }
            if log_positions {
                log::debug!("pet {idx}: ({:.1}, {:.1})", pet.state.x, pet.state.y);
            }
            pet.render(gpu);
        }
    }

    pub fn len(&self) -> usize { self.pets.len() }

    pub fn is_empty(&self) -> bool { self.pets.is_empty() }
}
