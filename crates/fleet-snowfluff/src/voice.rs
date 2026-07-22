//! Voice playback (tasks 10.1-10.5). Loads each language's manifest and
//! resolves clip keys on the main thread at startup; actual audio
//! playback happens on its own dedicated thread so a possibly-non-Send
//! rodio device handle never has to live inside the `Mutex<PetManager>`
//! state Tauri manages (same reasoning as the tick loop's background
//! thread, just for audio instead of rendering).

use std::{collections::HashMap, sync::mpsc};

use fleet_snowfluff_core::{resolve_voice_language, ClipSelector, VoiceLanguage, VoiceManifest};
use rodio::source::Source;

use crate::assets::VoiceAssets;

enum Command {
    /// `key` is the embedded asset path, e.g. `"zh/嗯.wav"`.
    Play {
        key: String,
        volume: f32,
    },
    Stop,
}

pub struct VoicePlayer {
    tx: Option<mpsc::Sender<Command>>,
    /// Embedded-asset keys (`"<lang>/<clip>"`), not filesystem paths.
    packs: HashMap<VoiceLanguage, Vec<String>>,
    languages_with_clips: Vec<VoiceLanguage>,
    active_language: VoiceLanguage,
    pub enabled: bool,
    /// 0.0-1.5, matching the legacy 0-150% range.
    volume: f32,
    selector: ClipSelector,
}

impl VoicePlayer {
    /// `requested_language` is the configured language, resolved
    /// against whichever packs actually have clips.
    pub fn new(requested_language: VoiceLanguage) -> Self {
        let mut packs = HashMap::new();
        let mut languages_with_clips = Vec::new();

        for lang in VoiceLanguage::ALL {
            let lang_dir = lang.asset_dir_name();
            let manifest_key = format!("{lang_dir}/manifest.json");
            let Some(manifest_file) = VoiceAssets::get(&manifest_key) else { continue };
            let Ok(text) = std::str::from_utf8(&manifest_file.data) else {
                log::warn!("voice: non-UTF8 manifest at {manifest_key}");
                continue;
            };
            let Ok(manifest) = serde_json::from_str::<VoiceManifest>(text) else {
                log::warn!("voice: malformed manifest at {manifest_key}");
                continue;
            };
            if manifest.has_clips() {
                let clip_keys = manifest.clips.iter().map(|c| format!("{lang_dir}/{c}")).collect();
                packs.insert(lang, clip_keys);
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
        let key = clips[index].clone();
        if let Some(tx) = &self.tx {
            let _ = tx.send(Command::Play { key, volume: self.volume });
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
                Command::Play { key, volume } => {
                    if let Some(p) = current.take() {
                        p.stop();
                    }
                    let Some(clip) = VoiceAssets::get(&key) else {
                        log::warn!("voice: bundled asset voice/{key} is missing");
                        continue;
                    };
                    let cursor = std::io::Cursor::new(clip.data.into_owned());
                    match rodio::Decoder::try_from(cursor) {
                        Ok(source) => {
                            let player = rodio::Player::connect_new(handle.mixer());
                            player.append(source.amplify(volume));
                            player.play();
                            current = Some(player);
                        }
                        Err(e) => log::warn!("voice: failed to decode voice/{key}: {e}"),
                    }
                }
            }
        }
    });
    Some(tx)
}
