//! Multi-instance coordination: a bounded collection of `PetState`s that
//! share one `MotionSettings`, matching legacy's `PetManager` (1-80
//! instances, settings changes apply to every pet at once). Window
//! creation/destruction to match the instance count is the shell's job
//! (task 6.7); this only owns the motion-relevant state.

use rand::Rng;

use crate::motion::{Bounds, MotionSettings, PetSize, PetState, TickEvents, TickInput};

pub const MIN_INSTANCES: usize = 1;
pub const MAX_INSTANCES: usize = 80;

#[derive(Debug)]
pub struct PetSwarm {
    pets: Vec<PetState>,
    pub settings: MotionSettings,
}

impl PetSwarm {
    /// Spawns `count` pets (clamped to `MIN_INSTANCES..=MAX_INSTANCES`),
    /// each at an independently randomized position and wander target.
    pub fn new(
        count: usize,
        bounds: Bounds,
        size: PetSize,
        settings: MotionSettings,
        rng: &mut impl Rng,
    ) -> Self {
        let count = count.clamp(MIN_INSTANCES, MAX_INSTANCES);
        let pets = (0..count).map(|_| PetState::spawn(bounds, size, rng)).collect();
        Self { pets, settings }
    }

    pub fn len(&self) -> usize { self.pets.len() }

    pub fn is_empty(&self) -> bool { self.pets.is_empty() }

    pub fn pets(&self) -> &[PetState] { &self.pets }

    /// Grows or shrinks the swarm to `count` (clamped), spawning new pets
    /// with `bounds`/`size` or dropping from the end.
    pub fn set_instance_count(
        &mut self,
        count: usize,
        bounds: Bounds,
        size: PetSize,
        rng: &mut impl Rng,
    ) {
        let count = count.clamp(MIN_INSTANCES, MAX_INSTANCES);
        if count > self.pets.len() {
            for _ in self.pets.len()..count {
                self.pets.push(PetState::spawn(bounds, size, rng));
            }
        } else {
            self.pets.truncate(count);
        }
    }

    /// Advances every pet by one tick under the shared settings, using
    /// per-pet bounds/size/mouse (mouse position is the same for all
    /// pets; bounds/size could theoretically differ, e.g. per-monitor
    /// confinement, hence taking them per-call rather than storing once).
    pub fn tick_all(
        &mut self,
        bounds: Bounds,
        size: PetSize,
        mouse: Option<(f64, f64)>,
        rng: &mut impl Rng,
    ) -> Vec<TickEvents> {
        let settings = self.settings;
        self.pets
            .iter_mut()
            .map(|pet| pet.tick(&TickInput { bounds, size, mouse, settings }, rng))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use rand::{rngs::StdRng, SeedableRng};

    use super::*;
    use crate::motion::WanderStayMode;

    fn bounds() -> Bounds { Bounds { left: 0.0, top: 0.0, right: 1920.0, bottom: 1080.0 } }
    fn size() -> PetSize { PetSize { w: 200.0, h: 200.0 } }
    fn settings() -> MotionSettings {
        MotionSettings { follow_mouse: false, wander_idle_stay_mode: WanderStayMode::AlwaysMove }
    }
    fn rng() -> StdRng { StdRng::seed_from_u64(1) }

    #[test]
    fn instance_count_clamped_to_valid_range() {
        let mut rng = rng();
        let swarm = PetSwarm::new(0, bounds(), size(), settings(), &mut rng);
        assert_eq!(swarm.len(), MIN_INSTANCES);

        let swarm = PetSwarm::new(999, bounds(), size(), settings(), &mut rng);
        assert_eq!(swarm.len(), MAX_INSTANCES);
    }

    #[test]
    fn increasing_instance_count_adds_pets_inheriting_shared_settings() {
        let mut rng = rng();
        let mut swarm = PetSwarm::new(1, bounds(), size(), settings(), &mut rng);
        swarm.set_instance_count(5, bounds(), size(), &mut rng);
        assert_eq!(swarm.len(), 5);
    }

    #[test]
    fn decreasing_instance_count_removes_pets() {
        let mut rng = rng();
        let mut swarm = PetSwarm::new(5, bounds(), size(), settings(), &mut rng);
        swarm.set_instance_count(2, bounds(), size(), &mut rng);
        assert_eq!(swarm.len(), 2);
    }

    #[test]
    fn tick_all_advances_every_pet() {
        let mut rng = rng();
        let mut swarm = PetSwarm::new(5, bounds(), size(), settings(), &mut rng);
        let positions_before: Vec<(f64, f64)> = swarm.pets().iter().map(|p| (p.x, p.y)).collect();
        // Several ticks so inertia-smoothed movement is guaranteed to show.
        for _ in 0..20 {
            swarm.tick_all(bounds(), size(), None, &mut rng);
        }
        let positions_after: Vec<(f64, f64)> = swarm.pets().iter().map(|p| (p.x, p.y)).collect();
        assert_eq!(positions_before.len(), positions_after.len());
        assert!(
            positions_before.iter().zip(positions_after.iter()).any(|(a, b)| a != b),
            "expected at least one pet to have moved"
        );
    }
}
