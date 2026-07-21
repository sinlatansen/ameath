pub mod config;
pub mod constants;
pub mod dock;
pub mod i18n;
pub mod locale;
pub mod motion;
pub mod pause;
pub mod swarm;
pub mod voice;

pub use config::Config;
pub use dock::{compute_dock_position, ForeignWindowRect};
pub use i18n::{dictionary, dictionary_json};
pub use locale::{detect_ui_language, resolve_ui_language, UiLanguage};
pub use motion::{
    Bounds, MotionSettings, MotionState, PetSize, PetState, TickEvents, TickInput, WanderStayMode,
};
pub use pause::{PauseAnimEvent, PauseAnimationScheduler};
pub use swarm::PetSwarm;
pub use voice::{resolve_voice_language, ClipSelector, VoiceLanguage, VoiceManifest};
