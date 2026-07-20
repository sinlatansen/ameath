//! Pause-mode random special-animation scheduling, ported from legacy's
//! `paused()` / `paused_to_idle()` two-phase cycle: rest quietly for
//! `PAUSE_ANIM_MIN_MS..PAUSE_ANIM_MAX_MS` (30-120s), then play one random
//! special animation for `STOP_DURATION_MIN_MS..STOP_DURATION_MAX_MS`
//! (4-8s), then repeat. Which animation asset to show is a rendering
//! concern; this only decides *when* to ask for a new one.

use rand::Rng;

use crate::constants::{
    PAUSE_ANIM_MAX_MS, PAUSE_ANIM_MIN_MS, STOP_DURATION_MAX_MS, STOP_DURATION_MIN_MS,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Phase {
    Idle,
    PlayingAnimation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PauseAnimEvent {
    /// Nothing changed this tick.
    None,
    /// Time to pick and play a new random special animation.
    PlayRandomAnimation,
    /// The special animation's duration elapsed; return to the idle/rest frame.
    ReturnToIdle,
}

#[derive(Debug, Clone)]
pub struct PauseAnimationScheduler {
    phase: Phase,
    timer_ms: i64,
}

impl PauseAnimationScheduler {
    pub fn new(rng: &mut impl Rng) -> Self {
        Self {
            phase: Phase::Idle,
            timer_ms: rng.random_range(PAUSE_ANIM_MIN_MS..=PAUSE_ANIM_MAX_MS),
        }
    }

    pub fn tick(&mut self, dt_ms: i64, rng: &mut impl Rng) -> PauseAnimEvent {
        self.timer_ms -= dt_ms;
        if self.timer_ms > 0 {
            return PauseAnimEvent::None;
        }
        match self.phase {
            Phase::Idle => {
                self.phase = Phase::PlayingAnimation;
                self.timer_ms = rng.random_range(STOP_DURATION_MIN_MS..=STOP_DURATION_MAX_MS);
                PauseAnimEvent::PlayRandomAnimation
            }
            Phase::PlayingAnimation => {
                self.phase = Phase::Idle;
                self.timer_ms = rng.random_range(PAUSE_ANIM_MIN_MS..=PAUSE_ANIM_MAX_MS);
                PauseAnimEvent::ReturnToIdle
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use rand::{rngs::StdRng, SeedableRng};

    use super::*;

    fn rng() -> StdRng { StdRng::seed_from_u64(7) }

    #[test]
    fn fires_play_animation_after_idle_interval_elapses() {
        let mut rng = rng();
        let mut scheduler = PauseAnimationScheduler::new(&mut rng);
        let mut event = PauseAnimEvent::None;
        // Enough ticks to guarantee we cross the max possible idle interval.
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
    fn returns_to_idle_after_animation_duration_elapses() {
        let mut rng = rng();
        let mut scheduler = PauseAnimationScheduler::new(&mut rng);

        // Drive to the first PlayRandomAnimation event.
        loop {
            if scheduler.tick(1000, &mut rng) == PauseAnimEvent::PlayRandomAnimation {
                break;
            }
        }

        let mut event = PauseAnimEvent::None;
        let ticks = (STOP_DURATION_MAX_MS / 500) + 2;
        for _ in 0..ticks {
            let e = scheduler.tick(500, &mut rng);
            if e != PauseAnimEvent::None {
                event = e;
                break;
            }
        }
        assert_eq!(event, PauseAnimEvent::ReturnToIdle);
    }

    #[test]
    fn no_event_on_first_tick() {
        let mut rng = rng();
        let mut scheduler = PauseAnimationScheduler::new(&mut rng);
        assert_eq!(scheduler.tick(1, &mut rng), PauseAnimEvent::None);
    }
}
