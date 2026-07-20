//! The pet motion state machine: wander / follow / curious / rest, inertia
//! movement, edge escape and respawn, and wander stay modes. Ported from
//! `legacy/ameath/pet.py`'s `move()` and its helpers (see design.md D4).
//!
//! Pause and drag are intentionally *not* modeled here: whether `tick()`
//! gets called at all on a given frame is the shell's decision (skip
//! calling it while paused or being dragged). This keeps the engine to
//! pure motion math, which is what makes it unit-testable headless.

use rand::Rng;

use crate::constants::*;

/// The pet's movable area, in absolute screen coordinates. Named
/// `left/top/right/bottom` (unlike legacy's confusingly-named
/// `screen_w`/`screen_h`, which were actually right/bottom coordinates,
/// not a width/height) for clarity; behavior is unchanged.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Bounds {
    pub left: f64,
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
}

impl Bounds {
    pub fn width(&self) -> f64 { self.right - self.left }

    pub fn height(&self) -> f64 { self.bottom - self.top }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PetSize {
    pub w: f64,
    pub h: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MotionState {
    Wander,
    Follow,
    Curious,
    Rest,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WanderStayMode {
    /// Always keep moving; idle animation plays without stopping.
    AlwaysMove,
    /// `STAY_PUT_CHANCE` chance to idle, and if idling, a 50/50 chance to
    /// keep moving while idling vs. stopping in place.
    Probabilistic,
    /// Always stop and idle in place.
    Stationary,
}

impl WanderStayMode {
    pub fn from_legacy_mode(mode: i32) -> Self {
        match mode {
            0 => Self::AlwaysMove,
            2 => Self::Stationary,
            _ => Self::Probabilistic,
        }
    }
}

/// Settings that can change at runtime (from user settings), passed into
/// each tick rather than owned by `PetState`, since they're shared across
/// every pet instance.
#[derive(Debug, Clone, Copy)]
pub struct MotionSettings {
    pub follow_mouse: bool,
    pub wander_idle_stay_mode: WanderStayMode,
}

/// Per-tick inputs that vary independent of settings.
#[derive(Debug, Clone, Copy)]
pub struct TickInput {
    pub bounds: Bounds,
    pub size: PetSize,
    /// Cursor position, in the same coordinate space as `bounds`. `None`
    /// when follow-mouse is disabled or the cursor position is unknown.
    pub mouse: Option<(f64, f64)>,
    pub settings: MotionSettings,
}

/// One-shot, edge-triggered outcomes of a tick, for the rendering layer
/// to react to (e.g. pick a new animation) without polling every field.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct TickEvents {
    /// The pet started idling this tick (random stop, or reaching a
    /// wander target and choosing to rest).
    pub started_idle: bool,
    /// The pet resumed moving this tick (idle/rest duration elapsed).
    pub resumed_moving: bool,
    /// Horizontal direction flipped this tick; sprite should mirror.
    pub direction_changed: bool,
    /// The pet escaped the bounds and respawned from the opposite edge.
    pub respawned: bool,
}

#[derive(Debug, Clone)]
pub struct PetState {
    pub x: f64,
    pub y: f64,
    pub vx: f64,
    pub vy: f64,
    pub target_x: f64,
    pub target_y: f64,
    target_timer: i32,
    pub motion_state: MotionState,
    rest_timer_ms: i64,
    /// Independent countdown started by `switch_to_idle`; mirrors
    /// legacy's `root.after(stop_duration, switch_to_move)`. Kept
    /// separate from `rest_timer_ms` because the two race independently
    /// in the legacy implementation (see design notes in this module).
    idle_stop_timer_ms: Option<i64>,
    pub moving_right: bool,
    pub is_moving: bool,
    pub is_idle_playing: bool,
    pub idle_allows_move: bool,
    jitter_x: f64,
    jitter_y: f64,
    tick_count: u32,
    last_mouse: Option<(f64, f64)>,
}

impl PetState {
    /// Spawns at a random position within `bounds`, with an initial
    /// random wander target, matching legacy's `__init__`.
    pub fn spawn(bounds: Bounds, size: PetSize, rng: &mut impl Rng) -> Self {
        let x = rng.random_range(bounds.left..=(bounds.right - size.w).max(bounds.left));
        let y = rng.random_range(bounds.top..=(bounds.bottom - size.h).max(bounds.top));
        let (target_x, target_y) = random_target(bounds, size, rng);
        Self {
            x,
            y,
            vx: SPEED_X,
            vy: SPEED_Y,
            target_x,
            target_y,
            target_timer: rng.random_range(TARGET_CHANGE_MIN_TICKS..=TARGET_CHANGE_MAX_TICKS),
            motion_state: MotionState::Wander,
            rest_timer_ms: 0,
            idle_stop_timer_ms: None,
            moving_right: true,
            is_moving: true,
            is_idle_playing: false,
            idle_allows_move: false,
            jitter_x: 0.0,
            jitter_y: 0.0,
            tick_count: 0,
            last_mouse: None,
        }
    }

    /// Advances the state machine by one tick (~`MOVE_INTERVAL_MS`).
    /// Caller is responsible for not calling this while paused or dragging.
    pub fn tick(&mut self, input: &TickInput, rng: &mut impl Rng) -> TickEvents {
        let mut events = TickEvents::default();

        // The idle-stop timer runs independent of the state machine below,
        // exactly as legacy's `root.after`-scheduled `switch_to_move` does.
        if let Some(remaining) = self.idle_stop_timer_ms.as_mut() {
            *remaining -= MOVE_INTERVAL_MS;
            if *remaining <= 0 {
                self.idle_stop_timer_ms = None;
                self.switch_to_move(&mut events);
            }
        }

        // Random stop-to-idle while wandering and moving.
        if self.motion_state == MotionState::Wander
            && self.is_moving
            && !self.is_idle_playing
            && rng.random_bool(STOP_CHANCE)
        {
            self.switch_to_idle(input.settings.wander_idle_stay_mode, rng, &mut events);
            return events;
        }

        if self.motion_state == MotionState::Rest {
            self.rest_timer_ms -= MOVE_INTERVAL_MS;
            if self.rest_timer_ms <= 0 {
                self.motion_state = MotionState::Wander;
                let (tx, ty) = random_target(input.bounds, input.size, rng);
                self.target_x = tx;
                self.target_y = ty;
                self.target_timer =
                    rng.random_range(TARGET_CHANGE_MIN_TICKS..=TARGET_CHANGE_MAX_TICKS);
                self.switch_to_move(&mut events);
            }
            return events;
        }

        if !self.is_moving {
            return events;
        }

        let mouse_moved = match input.mouse {
            Some(m) => {
                let moved = self.last_mouse != Some(m);
                self.last_mouse = Some(m);
                moved
            }
            None => false,
        };

        let mut dx = self.target_x - self.x;
        let mut dy = self.target_y - self.y;
        let mut dist = (dx * dx + dy * dy).sqrt();

        if !input.settings.follow_mouse
            && matches!(self.motion_state, MotionState::Follow | MotionState::Curious)
        {
            self.motion_state = MotionState::Wander;
        }

        if input.settings.follow_mouse {
            if let Some((mx, my)) = input.mouse {
                let dist_mouse = ((mx - self.x).powi(2) + (my - self.y).powi(2)).sqrt();
                if dist_mouse > FOLLOW_START_DIST {
                    self.motion_state = MotionState::Follow;
                } else if dist_mouse < FOLLOW_STOP_DIST {
                    self.motion_state = MotionState::Curious;
                }
            }
        } else if self.motion_state == MotionState::Wander && dist < REST_DISTANCE {
            if rng.random_bool(REST_CHANCE) {
                if input.settings.wander_idle_stay_mode == WanderStayMode::AlwaysMove {
                    let (tx, ty) = random_target(input.bounds, input.size, rng);
                    self.target_x = tx;
                    self.target_y = ty;
                    self.target_timer =
                        rng.random_range(TARGET_CHANGE_MIN_TICKS..=TARGET_CHANGE_MAX_TICKS);
                } else if !self.is_idle_playing {
                    self.motion_state = MotionState::Rest;
                    self.rest_timer_ms =
                        rng.random_range(REST_DURATION_MIN_MS..=REST_DURATION_MAX_MS);
                    self.switch_to_idle(input.settings.wander_idle_stay_mode, rng, &mut events);
                    return events;
                }
            } else {
                let (tx, ty) = random_target(input.bounds, input.size, rng);
                self.target_x = tx;
                self.target_y = ty;
                self.target_timer =
                    rng.random_range(TARGET_CHANGE_MIN_TICKS..=TARGET_CHANGE_MAX_TICKS);
            }
        }

        if self.motion_state == MotionState::Wander {
            self.target_timer -= 1;
            if self.target_timer <= 0 {
                let (tx, ty) = random_target(input.bounds, input.size, rng);
                self.target_x = tx;
                self.target_y = ty;
                self.target_timer =
                    rng.random_range(TARGET_CHANGE_MIN_TICKS..=TARGET_CHANGE_MAX_TICKS);
            }
        }

        let speed_mul = match self.motion_state {
            MotionState::Wander => SPEED_WANDER,
            MotionState::Follow => SPEED_FOLLOW,
            MotionState::Curious => SPEED_CURIOUS,
            MotionState::Rest => 1.0,
        };

        if matches!(self.motion_state, MotionState::Follow | MotionState::Curious) && mouse_moved {
            if let Some((mx, my)) = input.mouse {
                let offset = if self.motion_state == MotionState::Follow {
                    FOLLOW_DISTANCE
                } else {
                    FOLLOW_STOP_DIST
                };
                self.target_x = mx + rng.random_range(-offset..=offset);
                self.target_y = my + rng.random_range(-offset..=offset);
                dx = self.target_x - self.x;
                dy = self.target_y - self.y;
                dist = (dx * dx + dy * dy).sqrt().max(1.0);
            }
        }

        let desired_vx = dx / dist * SPEED_X * speed_mul;
        let desired_vy = dy / dist * SPEED_Y * speed_mul;
        self.vx = self.vx * INERTIA_FACTOR + desired_vx * INTENT_FACTOR;
        self.vy = self.vy * INERTIA_FACTOR + desired_vy * INTENT_FACTOR;

        self.tick_count += 1;
        if self.tick_count.is_multiple_of(JITTER_INTERVAL_TICKS) {
            self.jitter_x = rng.random_range(-JITTER..=JITTER);
            self.jitter_y = rng.random_range(-JITTER..=JITTER);
        }
        self.vx += self.jitter_x;
        self.vy += self.jitter_y;

        self.x += self.vx;
        self.y += self.vy;

        let respawned = self.handle_edge(input.bounds, input.size, rng);
        events.respawned = respawned;
        if !respawned {
            let mut hit_edge = false;
            if self.x <= input.bounds.left {
                self.x = input.bounds.left;
                self.vx = self.vx.abs();
                hit_edge = true;
            } else if self.x + input.size.w >= input.bounds.right {
                self.x = input.bounds.right - input.size.w;
                self.vx = -self.vx.abs();
                hit_edge = true;
            }
            if self.y <= input.bounds.top {
                self.y = input.bounds.top;
                self.vy = self.vy.abs();
                hit_edge = true;
            } else if self.y + input.size.h >= input.bounds.bottom {
                self.y = input.bounds.bottom - input.size.h;
                self.vy = -self.vy.abs();
                hit_edge = true;
            }

            let new_moving_right = self.vx > 0.5;
            let new_moving_left = self.vx < -0.5;
            if self.is_idle_playing {
                hit_edge = false;
            }
            let _ = hit_edge; // kept for parity with legacy; not otherwise consumed
            if new_moving_right && !self.moving_right && !self.is_idle_playing {
                self.moving_right = true;
                events.direction_changed = true;
            } else if new_moving_left && self.moving_right && !self.is_idle_playing {
                self.moving_right = false;
                events.direction_changed = true;
            }
        }

        events
    }

    fn switch_to_idle(
        &mut self,
        mode: WanderStayMode,
        rng: &mut impl Rng,
        events: &mut TickEvents,
    ) {
        self.is_idle_playing = false;
        self.idle_allows_move = false;

        match mode {
            WanderStayMode::AlwaysMove => {
                self.is_idle_playing = true;
                self.idle_allows_move = true;
                self.is_moving = true;
            }
            WanderStayMode::Stationary => {
                self.is_idle_playing = true;
                self.idle_allows_move = false;
                self.is_moving = false;
            }
            WanderStayMode::Probabilistic => {
                if rng.random_bool(STAY_PUT_CHANCE) {
                    self.is_idle_playing = true;
                    self.idle_allows_move = rng.random_bool(0.5);
                    self.is_moving = self.idle_allows_move;
                } else {
                    self.is_idle_playing = false;
                    self.idle_allows_move = false;
                    self.is_moving = false;
                }
            }
        }

        self.idle_stop_timer_ms =
            Some(rng.random_range(STOP_DURATION_MIN_MS..=STOP_DURATION_MAX_MS));
        events.started_idle = true;
    }

    fn switch_to_move(&mut self, events: &mut TickEvents) {
        self.is_idle_playing = false;
        self.idle_allows_move = false;
        self.is_moving = true;
        events.resumed_moving = true;
    }

    /// Returns `true` if the pet escaped bounds and respawned from the
    /// opposite edge; `false` if it stayed in bounds or bounced back.
    fn handle_edge(&mut self, bounds: Bounds, size: PetSize, rng: &mut impl Rng) -> bool {
        let mut escaped = false;
        if self.x < bounds.left || self.x > bounds.right - size.w {
            escaped = true;
        }
        if self.y < bounds.top || self.y > bounds.bottom - size.h {
            escaped = true;
        }

        if escaped {
            if rng.random_bool(EDGE_ESCAPE_CHANCE) {
                self.respawn_from_edge(bounds, size, rng);
                return true;
            }
            self.vx = -self.vx;
            self.vy = -self.vy;
            self.x = self.x.clamp(bounds.left, bounds.right - size.w);
            self.y = self.y.clamp(bounds.top, bounds.bottom - size.h);
        }
        false
    }

    fn respawn_from_edge(&mut self, bounds: Bounds, size: PetSize, rng: &mut impl Rng) {
        match rng.random_range(0..4) {
            0 => {
                self.x = bounds.left - RESPAWN_MARGIN;
                self.y = rng.random_range(bounds.top..=(bounds.bottom - size.h).max(bounds.top));
            }
            1 => {
                self.x = bounds.right + RESPAWN_MARGIN;
                self.y = rng.random_range(bounds.top..=(bounds.bottom - size.h).max(bounds.top));
            }
            2 => {
                self.y = bounds.top - RESPAWN_MARGIN;
                self.x = rng.random_range(bounds.left..=(bounds.right - size.w).max(bounds.left));
            }
            _ => {
                self.y = bounds.bottom + RESPAWN_MARGIN;
                self.x = rng.random_range(bounds.left..=(bounds.right - size.w).max(bounds.left));
            }
        }
        self.vx = if rng.random_bool(0.5) { -3.0 } else { 3.0 };
        self.vy = rng.random_range(-2..=2) as f64;
    }
}

/// Random wander target, occasionally placed just outside `bounds` to
/// trigger edge-escape behavior, matching legacy's `get_random_target`.
fn random_target(bounds: Bounds, size: PetSize, rng: &mut impl Rng) -> (f64, f64) {
    if rng.random_bool(OUTSIDE_TARGET_CHANCE) {
        let margin = RESPAWN_MARGIN + 50.0;
        match rng.random_range(0..4) {
            0 => (
                bounds.left - margin,
                rng.random_range(bounds.top..=(bounds.bottom - size.h).max(bounds.top)),
            ),
            1 => (
                bounds.right + margin,
                rng.random_range(bounds.top..=(bounds.bottom - size.h).max(bounds.top)),
            ),
            2 => (
                rng.random_range(bounds.left..=(bounds.right - size.w).max(bounds.left)),
                bounds.top - margin,
            ),
            _ => (
                rng.random_range(bounds.left..=(bounds.right - size.w).max(bounds.left)),
                bounds.bottom + margin,
            ),
        }
    } else {
        (
            rng.random_range(bounds.left..=(bounds.right - size.w).max(bounds.left)),
            rng.random_range(bounds.top..=(bounds.bottom - size.h).max(bounds.top)),
        )
    }
}

#[cfg(test)]
mod tests {
    use rand::{rngs::StdRng, SeedableRng};

    use super::*;

    fn bounds() -> Bounds { Bounds { left: 0.0, top: 0.0, right: 1920.0, bottom: 1080.0 } }
    fn size() -> PetSize { PetSize { w: 200.0, h: 200.0 } }
    fn settings_wander() -> MotionSettings {
        MotionSettings { follow_mouse: false, wander_idle_stay_mode: WanderStayMode::AlwaysMove }
    }

    fn rng() -> StdRng { StdRng::seed_from_u64(42) }

    #[test]
    fn spawn_places_pet_within_bounds() {
        let mut rng = rng();
        let state = PetState::spawn(bounds(), size(), &mut rng);
        assert!(state.x >= bounds().left && state.x <= bounds().right - size().w);
        assert!(state.y >= bounds().top && state.y <= bounds().bottom - size().h);
        assert_eq!(state.motion_state, MotionState::Wander);
        assert!(state.is_moving);
    }

    #[test]
    fn follow_engages_beyond_start_distance() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        state.x = 500.0;
        state.y = 500.0;
        let input = TickInput {
            bounds: bounds(),
            size: size(),
            mouse: Some((500.0 + FOLLOW_START_DIST + 50.0, 500.0)),
            settings: MotionSettings {
                follow_mouse: true,
                wander_idle_stay_mode: WanderStayMode::AlwaysMove,
            },
        };
        state.tick(&input, &mut rng);
        assert_eq!(state.motion_state, MotionState::Follow);
    }

    #[test]
    fn curious_engages_within_stop_distance() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        state.motion_state = MotionState::Follow;
        state.x = 500.0;
        state.y = 500.0;
        let input = TickInput {
            bounds: bounds(),
            size: size(),
            mouse: Some((500.0 + FOLLOW_STOP_DIST - 10.0, 500.0)),
            settings: MotionSettings {
                follow_mouse: true,
                wander_idle_stay_mode: WanderStayMode::AlwaysMove,
            },
        };
        state.tick(&input, &mut rng);
        assert_eq!(state.motion_state, MotionState::Curious);
    }

    #[test]
    fn disabling_follow_mouse_resets_to_wander() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        state.motion_state = MotionState::Follow;
        let input =
            TickInput { bounds: bounds(), size: size(), mouse: None, settings: settings_wander() };
        state.tick(&input, &mut rng);
        assert_eq!(state.motion_state, MotionState::Wander);
    }

    #[test]
    fn rest_state_counts_down_and_returns_to_wander() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        state.motion_state = MotionState::Rest;
        state.is_idle_playing = true;
        // rest_timer_ms is private; drive it down via repeated ticks using
        // the public API only, by forcing a short rest through the normal
        // near-target path instead of poking internals.
        state.x = state.target_x;
        state.y = state.target_y;

        let input =
            TickInput { bounds: bounds(), size: size(), mouse: None, settings: settings_wander() };

        // Rest duration is at most REST_DURATION_MAX_MS; enough ticks must
        // return the state machine to Wander.
        let max_ticks = (REST_DURATION_MAX_MS / MOVE_INTERVAL_MS) + 2;
        for _ in 0..max_ticks {
            state.tick(&input, &mut rng);
            if state.motion_state == MotionState::Wander {
                break;
            }
        }
        assert_eq!(state.motion_state, MotionState::Wander);
        assert!(state.is_moving);
    }

    #[test]
    fn stationary_wander_stay_mode_holds_position_while_idle() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        let mut events = TickEvents::default();
        state.switch_to_idle(WanderStayMode::Stationary, &mut rng, &mut events);
        assert!(state.is_idle_playing);
        assert!(!state.is_moving);
        assert!(!state.idle_allows_move);
    }

    #[test]
    fn always_move_wander_stay_mode_keeps_moving_while_idle() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        let mut events = TickEvents::default();
        state.switch_to_idle(WanderStayMode::AlwaysMove, &mut rng, &mut events);
        assert!(state.is_idle_playing);
        assert!(state.is_moving);
        assert!(state.idle_allows_move);
    }

    #[test]
    fn inertia_smooths_direction_change_over_multiple_ticks() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        state.x = 500.0;
        state.y = 500.0;
        state.vx = 3.0;
        state.vy = 0.0;
        // Snap the target to the opposite direction abruptly.
        state.target_x = 0.0;
        state.target_y = 500.0;
        state.target_timer = TARGET_CHANGE_MAX_TICKS;

        let input =
            TickInput { bounds: bounds(), size: size(), mouse: None, settings: settings_wander() };
        let vx_before = state.vx;
        state.tick(&input, &mut rng);
        let vx_after_one_tick = state.vx;

        // One tick should not fully reverse velocity; inertia dominates.
        assert!(vx_after_one_tick > 0.0, "velocity should not snap negative in one tick");
        assert!(vx_after_one_tick < vx_before, "velocity should trend toward the new target");
    }

    #[test]
    fn respawn_places_pet_outside_bounds_near_an_edge() {
        let mut rng = rng();
        let mut state = PetState::spawn(bounds(), size(), &mut rng);
        state.respawn_from_edge(bounds(), size(), &mut rng);
        let outside_left = state.x <= bounds().left;
        let outside_right = state.x >= bounds().right;
        let outside_top = state.y <= bounds().top;
        let outside_bottom = state.y >= bounds().bottom;
        assert!(
            outside_left || outside_right || outside_top || outside_bottom,
            "respawned position ({}, {}) should be outside bounds",
            state.x,
            state.y
        );
    }

    #[test]
    fn random_target_stays_mostly_within_or_just_outside_bounds() {
        let mut rng = rng();
        for _ in 0..200 {
            let (tx, ty) = random_target(bounds(), size(), &mut rng);
            let margin = RESPAWN_MARGIN + 50.0 + 1.0;
            assert!(tx >= bounds().left - margin && tx <= bounds().right + margin);
            assert!(ty >= bounds().top - margin && ty <= bounds().bottom + margin);
        }
    }
}
