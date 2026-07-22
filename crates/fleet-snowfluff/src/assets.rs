//! GIF and voice assets are embedded straight into the binary via
//! `rust-embed` (task 16-adjacent: this is exactly the "bundled
//! resources" wiring that comment used to say was still pending).
//! `#[folder = "../../assets/..."]` resolves relative to this crate's
//! `Cargo.toml` at compile time -- same relative path the old
//! filesystem-based `assets_dir()` used.
//!
//! In debug builds, `rust-embed` reads straight from disk at runtime
//! instead of actually embedding (unless the `debug-embed` feature is
//! turned on, which it isn't here) -- editing a GIF or voice clip and
//! re-running `just dev` picks it up without a rebuild, same as
//! before. Release and cross builds (`just build`, `just build-
//! windows`) embed for real, which is the whole point: the resulting
//! binary is self-contained and doesn't need `assets/` copied
//! alongside it to run.

use rust_embed::RustEmbed;

#[derive(RustEmbed)]
#[folder = "../../assets/gifs/"]
pub struct GifAssets;

#[derive(RustEmbed)]
#[folder = "../../assets/voice/"]
pub struct VoiceAssets;

/// Reads an embedded GIF by filename (e.g. `"move.gif"`), panicking if
/// it's missing -- every name this is called with comes from
/// `animation::load_animation_set`'s fixed, known list, so a miss means
/// the `assets/gifs/` directory itself is broken, not bad user input.
pub fn gif_bytes(name: &str) -> std::borrow::Cow<'static, [u8]> {
    GifAssets::get(name).unwrap_or_else(|| panic!("bundled asset gifs/{name} is missing")).data
}
