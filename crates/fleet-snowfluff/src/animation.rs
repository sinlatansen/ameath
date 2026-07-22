//! GIF animation loading (task 6.3/6.4). Frames are decoded once at
//! native resolution and kept that way — scale (task 6.5) is applied by
//! resizing the *window*, not by re-rasterizing frames, so changing scale
//! is just a resize, not a reload.

use std::time::Duration;

use image::{AnimationDecoder, RgbaImage};

use crate::assets::gif_bytes;

#[derive(Debug, Clone)]
pub struct AnimationFrame {
    pub rgba: Vec<u8>,
    pub delay: Duration,
}

#[derive(Debug, Clone)]
pub struct AnimationClip {
    pub frames: Vec<AnimationFrame>,
    pub width: u32,
    pub height: u32,
}

impl AnimationClip {
    fn from_rgba_frames(frames: Vec<(RgbaImage, Duration)>) -> Self {
        let width = frames.first().map(|(img, _)| img.width()).unwrap_or(1);
        let height = frames.first().map(|(img, _)| img.height()).unwrap_or(1);
        let frames = frames
            .into_iter()
            .map(|(img, delay)| AnimationFrame {
                rgba: img.into_raw(),
                delay: if delay.is_zero() { Duration::from_millis(80) } else { delay },
            })
            .collect();
        Self { frames, width, height }
    }

    fn flipped_horizontally(&self, source: &[(RgbaImage, Duration)]) -> Self {
        let flipped: Vec<(RgbaImage, Duration)> = source
            .iter()
            .map(|(img, delay)| (image::imageops::flip_horizontal(img), *delay))
            .collect();
        Self::from_rgba_frames(flipped)
    }
}

/// Which animation should currently be displayed, mirroring the fields
/// `PetState`/pause logic exposes -- selection lives here, in the shell,
/// since core has no notion of animation assets (D2).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnimationCue {
    Move,
    Idle(usize),
    Drag,
    Paused,
    Screen(usize),
}

pub struct AnimationSet {
    pub move_right: AnimationClip,
    pub move_left: AnimationClip,
    pub idle: Vec<AnimationClip>,
    pub drag: AnimationClip,
    pub paused: AnimationClip,
    pub screen: Vec<AnimationClip>,
}

impl AnimationSet {
    pub fn clip_for(&self, cue: AnimationCue, moving_right: bool) -> &AnimationClip {
        match cue {
            AnimationCue::Move => {
                if moving_right {
                    &self.move_right
                } else {
                    &self.move_left
                }
            }
            AnimationCue::Idle(i) => &self.idle[i % self.idle.len().max(1)],
            AnimationCue::Drag => &self.drag,
            AnimationCue::Paused => &self.paused,
            AnimationCue::Screen(i) => &self.screen[i % self.screen.len().max(1)],
        }
    }
}

fn decode_gif_frames(name: &str) -> Vec<(RgbaImage, Duration)> {
    let bytes = gif_bytes(name);
    let decoder = image::codecs::gif::GifDecoder::new(std::io::Cursor::new(bytes))
        .unwrap_or_else(|e| panic!("failed to decode gifs/{name}: {e}"));
    decoder
        .into_frames()
        .collect_frames()
        .unwrap_or_else(|e| panic!("failed to collect frames from gifs/{name}: {e}"))
        .into_iter()
        .map(|frame| {
            let delay: Duration = frame.delay().into();
            (frame.into_buffer(), delay)
        })
        .collect()
}

fn load_clip(name: &str) -> AnimationClip {
    AnimationClip::from_rgba_frames(decode_gif_frames(name))
}

/// Loads every animation the pet needs, matching legacy's `__init__`
/// asset loading (move/idle1-4/drag/idle2-as-paused/screen1-7).
pub fn load_animation_set() -> AnimationSet {
    let move_source = decode_gif_frames("move.gif");
    let move_right = AnimationClip::from_rgba_frames(move_source.clone());
    let move_left = move_right.flipped_horizontally(&move_source);

    let idle = (1..=4).map(|i| load_clip(&format!("idle{i}.gif"))).collect();
    let screen = (1..=7).map(|i| load_clip(&format!("screen{i}.gif"))).collect();
    let drag = load_clip("drag.gif");
    let paused = load_clip("idle2.gif");

    AnimationSet { move_right, move_left, idle, drag, paused, screen }
}
