pub mod constants;
pub mod dock;
pub mod motion;
pub mod pause;
pub mod swarm;

pub use dock::{compute_dock_position, ForeignWindowRect};
pub use motion::{
    Bounds, MotionSettings, MotionState, PetSize, PetState, TickEvents, TickInput, WanderStayMode,
};
pub use pause::{PauseAnimEvent, PauseAnimationScheduler};
pub use swarm::PetSwarm;
