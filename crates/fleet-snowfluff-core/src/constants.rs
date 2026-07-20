//! Tuning constants ported from the legacy `ameath/constants.py`. Values
//! are unchanged from the Python original so the pet's motion "feel"
//! matches `legacy/` exactly (see design.md D4).

/// Base per-axis speed (px/tick) before per-state speed multipliers.
pub const SPEED_X: f64 = 3.0;
pub const SPEED_Y: f64 = 2.0;

/// Per-tick probability a wandering, moving pet stops to idle.
pub const STOP_CHANCE: f64 = 0.003;
pub const STOP_DURATION_MIN_MS: i64 = 4_000;
pub const STOP_DURATION_MAX_MS: i64 = 8_000;

/// Motion tick cadence (~33fps), matching legacy's `MOVE_INTERVAL`.
pub const MOVE_INTERVAL_MS: i64 = 30;
/// Jitter is re-rolled every N ticks rather than every tick.
pub const JITTER_INTERVAL_TICKS: u32 = 5;

/// Probability an out-of-bounds pet respawns from the opposite edge
/// instead of bouncing back in.
pub const EDGE_ESCAPE_CHANCE: f64 = 0.3;
pub const RESPAWN_MARGIN: f64 = 50.0;

/// Wander target re-roll cadence, in ticks.
pub const TARGET_CHANGE_MIN_TICKS: i32 = 200;
pub const TARGET_CHANGE_MAX_TICKS: i32 = 500;
/// Probability a wander target is chosen just outside the bounds.
pub const OUTSIDE_TARGET_CHANCE: f64 = 0.4;

pub const FOLLOW_DISTANCE: f64 = 80.0;

/// Inertia blend: new velocity = old * INERTIA_FACTOR + desired *
/// INTENT_FACTOR.
pub const INERTIA_FACTOR: f64 = 0.95;
pub const INTENT_FACTOR: f64 = 0.05;
pub const JITTER: f64 = 0.15;

/// Probability a wandering pet rests on reaching its target.
pub const REST_CHANCE: f64 = 0.6;
pub const REST_DURATION_MIN_MS: i64 = 1_000;
pub const REST_DURATION_MAX_MS: i64 = 3_000;
pub const REST_DISTANCE: f64 = 20.0;

/// Pause-mode random special-animation interval.
pub const PAUSE_ANIM_MIN_MS: i64 = 30_000;
pub const PAUSE_ANIM_MAX_MS: i64 = 120_000;

pub const FOLLOW_START_DIST: f64 = 200.0;
pub const FOLLOW_STOP_DIST: f64 = 60.0;

pub const SPEED_WANDER: f64 = 0.8;
pub const SPEED_FOLLOW: f64 = 1.2;
pub const SPEED_CURIOUS: f64 = 0.5;

/// Probability a probabilistic-stay pet that decides to idle also stays
/// put (vs. idle-while-still-moving).
pub const STAY_PUT_CHANCE: f64 = 0.3;

/// Scale steps: 0.1x .. 2.0x in 0.1 increments (20 values).
pub fn scale_options() -> Vec<f64> { (1..=20).map(|i| i as f64 / 10.0).collect() }
pub const DEFAULT_SCALE_INDEX: usize = 9;

/// Opacity steps: 10% .. 100% in 10% increments (10 values).
pub fn transparency_options() -> Vec<f64> { (1..=10).map(|i| i as f64 / 10.0).collect() }
pub const DEFAULT_TRANSPARENCY_INDEX: usize = 9;

pub const DEFAULT_SCREEN_INDEX: i32 = 0;
pub const DEFAULT_WANDER_IDLE_STAY_MODE: i32 = 2;
pub const DEFAULT_VOICE_ENABLED: bool = true;
pub const DEFAULT_VOICE_VOLUME: i32 = 100;
