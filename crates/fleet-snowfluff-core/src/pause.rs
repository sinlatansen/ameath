//! Pause-mode (window-snap) random special-animation scheduling. Rests
//! quietly for a fixed `PAUSE_IDLE_MS`, then keeps switching to a
//! different random screen-reaction gif every
//! `PAUSE_ANIM_MIN_MS..PAUSE_ANIM_MAX_MS` for as long as the pet stays
//! paused. Which animation asset to show is a rendering concern; this
//! only decides *when* to ask for a new one.

use rand::Rng;

use crate::constants::{PAUSE_ANIM_MAX_MS, PAUSE_ANIM_MIN_MS, PAUSE_IDLE_MS};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PauseAnimEvent {
    /// Nothing changed this tick.
    None,
    /// Time to switch to a new random screen-reaction animation.
    PlayRandomAnimation,
}

#[derive(Debug, Clone)]
pub struct PauseAnimationScheduler {
    timer_ms: i64,
}

impl Default for PauseAnimationScheduler {
    fn default() -> Self { Self::new() }
}

impl PauseAnimationScheduler {
    pub fn new() -> Self { Self { timer_ms: PAUSE_IDLE_MS } }

    pub fn tick(&mut self, dt_ms: i64, rng: &mut impl Rng) -> PauseAnimEvent {
        self.timer_ms -= dt_ms;
        if self.timer_ms > 0 {
            return PauseAnimEvent::None;
        }
        self.timer_ms = rng.random_range(PAUSE_ANIM_MIN_MS..=PAUSE_ANIM_MAX_MS);
        PauseAnimEvent::PlayRandomAnimation
    }
}

#[cfg(test)]
mod tests {
    use rand::{rngs::StdRng, SeedableRng};

    use super::*;

    fn rng() -> StdRng { StdRng::seed_from_u64(7) }

    #[test]
    fn fires_play_animation_after_the_fixed_idle_delay() {
        let mut rng = rng();
        let mut scheduler = PauseAnimationScheduler::new();

        for _ in 0..(PAUSE_IDLE_MS / 1000 - 1) {
            assert_eq!(scheduler.tick(1000, &mut rng), PauseAnimEvent::None);
        }
        assert_eq!(scheduler.tick(2000, &mut rng), PauseAnimEvent::PlayRandomAnimation);
    }

    #[test]
    fn keeps_firing_play_animation_on_the_30_120s_cycle_after_that() {
        let mut rng = rng();
        let mut scheduler = PauseAnimationScheduler::new();

        // Drive past the initial fixed idle delay.
        loop {
            if scheduler.tick(1000, &mut rng) == PauseAnimEvent::PlayRandomAnimation {
                break;
            }
        }

        let mut event = PauseAnimEvent::None;
        let ticks = (PAUSE_ANIM_MAX_MS / 1000) + 2;
        for _ in 0..ticks {
            let e = scheduler.tick(1000, &mut rng);
            if e != PauseAnimEvent::None {
                event = e;
                break;
            }
        }
        assert_eq!(event, PauseAnimEvent::PlayRandomAnimation);
    }

    #[test]
    fn no_event_on_first_tick() {
        let mut rng = rng();
        let mut scheduler = PauseAnimationScheduler::new();
        assert_eq!(scheduler.tick(1, &mut rng), PauseAnimEvent::None);
    }
}
