//! Voice playback (tasks 10.1-10.5). Loads each language's manifest and
//! resolves clip paths on the main thread at startup; actual audio
//! playback happens on its own dedicated thread so a possibly-non-Send
//! rodio device handle never has to live inside the `Mutex<PetManager>`
//! state Tauri manages (same reasoning as the tick loop's background
//! thread, just for audio instead of rendering).

use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::mpsc,
};

use fleet_snowfluff_core::{resolve_voice_language, ClipSelector, VoiceLanguage, VoiceManifest};
use rodio::source::Source;

enum Command {
    Play { path: PathBuf, volume: f32 },
    Stop,
}

pub struct VoicePlayer {
    tx: Option<mpsc::Sender<Command>>,
    packs: HashMap<VoiceLanguage, Vec<PathBuf>>,
    languages_with_clips: Vec<VoiceLanguage>,
    active_language: VoiceLanguage,
    pub enabled: bool,
    /// 0.0-1.5, matching the legacy 0-150% range.
    volume: f32,
    selector: ClipSelector,
}

impl VoicePlayer {
    /// `voice_dir` is `assets/voice/`; `requested_language` is the
    /// configured language, resolved against whichever packs actually
    /// have clips (only `zh` ships initially).
    pub fn new(voice_dir: &Path, requested_language: VoiceLanguage) -> Self {
        let mut packs = HashMap::new();
        let mut languages_with_clips = Vec::new();

        for lang in VoiceLanguage::ALL {
            let lang_dir = voice_dir.join(lang.asset_dir_name());
            let manifest_path = lang_dir.join("manifest.json");
            let Ok(text) = std::fs::read_to_string(&manifest_path) else { continue };
            let Ok(manifest) = serde_json::from_str::<VoiceManifest>(&text) else {
                log::warn!("voice: malformed manifest at {manifest_path:?}");
                continue;
            };
            if manifest.has_clips() {
                let clip_paths = manifest.clips.iter().map(|c| lang_dir.join(c)).collect();
                packs.insert(lang, clip_paths);
                languages_with_clips.push(lang);
            }
        }

        let active_language = resolve_voice_language(requested_language, &languages_with_clips);
        let tx = spawn_audio_thread();

        Self {
            tx,
            packs,
            languages_with_clips,
            active_language,
            enabled: true,
            volume: 1.0,
            selector: ClipSelector::new(),
        }
    }

    pub fn languages_with_clips(&self) -> &[VoiceLanguage] { &self.languages_with_clips }

    pub fn active_language(&self) -> VoiceLanguage { self.active_language }

    pub fn set_language(&mut self, requested: VoiceLanguage) {
        self.active_language = resolve_voice_language(requested, &self.languages_with_clips);
    }

    /// `percent` is 0-150; out-of-range values are clamped rather than
    /// rejected (the config layer already validates the persisted value).
    pub fn set_volume_percent(&mut self, percent: i64) {
        self.volume = (percent as f32 / 100.0).clamp(0.0, 1.5);
    }

    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
        if !enabled {
            self.stop();
        }
    }

    pub fn stop(&self) {
        if let Some(tx) = &self.tx {
            let _ = tx.send(Command::Stop);
        }
    }

    /// Plays a random clip from the active pack, avoiding a 4th
    /// consecutive repeat; stops whatever is currently playing first
    /// (matches legacy's `play_random_voice`). No-op if voice is
    /// disabled or the active pack is empty (shouldn't happen given the
    /// resolve_voice_language invariant, but a missing/unreadable file
    /// could still make a pack empty at runtime).
    pub fn play_random(&mut self) {
        if !self.enabled {
            return;
        }
        let Some(clips) = self.packs.get(&self.active_language) else { return };
        if clips.is_empty() {
            return;
        }
        let mut rng = rand::rng();
        let index = self.selector.pick(clips.len(), &mut rng);
        let path = clips[index].clone();
        if let Some(tx) = &self.tx {
            let _ = tx.send(Command::Play { path, volume: self.volume });
        }
    }
}

/// Spawns the audio thread and returns a sender to it, or `None` if no
/// output device is available (headless CI, muted/disconnected audio,
/// etc.) -- voice simply becomes a no-op rather than failing startup.
fn spawn_audio_thread() -> Option<mpsc::Sender<Command>> {
    let (tx, rx) = mpsc::channel::<Command>();
    std::thread::spawn(move || {
        let handle = match rodio::DeviceSinkBuilder::open_default_sink() {
            Ok(h) => h,
            Err(e) => {
                log::warn!("voice: no audio output device available ({e}); voice disabled");
                return;
            }
        };
        let mut current: Option<rodio::Player> = None;

        for cmd in rx {
            match cmd {
                Command::Stop => {
                    if let Some(p) = current.take() {
                        p.stop();
                    }
                }
                Command::Play { path, volume } => {
                    if let Some(p) = current.take() {
                        p.stop();
                    }
                    match std::fs::File::open(&path).map(rodio::Decoder::try_from) {
                        Ok(Ok(source)) => {
                            let player = rodio::Player::connect_new(handle.mixer());
                            player.append(source.amplify(volume));
                            player.play();
                            current = Some(player);
                        }
                        Ok(Err(e)) => log::warn!("voice: failed to decode {path:?}: {e}"),
                        Err(e) => log::warn!("voice: failed to open {path:?}: {e}"),
                    }
                }
            }
        }
    });
    Some(tx)
}
