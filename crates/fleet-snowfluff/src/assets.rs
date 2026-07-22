//! Asset path resolution. In a bundled build, GIFs ship as Tauri
//! resources; that wiring lands with the release pipeline (task 16).
//! Until then, two cases matter: running in place in the workspace
//! (`just dev`/`just build`, where `CARGO_MANIFEST_DIR` -- a path
//! baked in at *compile* time on the build machine -- correctly points
//! at `assets/`), and running a binary that's been copied somewhere
//! else entirely (task 16's `build-windows`/`build-linux`: cross/
//! container-built, then copied to different hardware to actually
//! test). `CARGO_MANIFEST_DIR` is nonsensical in the second case -- a
//! macOS path has no meaning at all on the Windows machine the binary
//! was copied to -- so this checks next to the running executable
//! first (where those recipes copy `assets/` alongside the binary)
//! and only falls back to the compile-time dev path if that's absent.
use std::path::PathBuf;

pub fn assets_dir() -> PathBuf {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let candidate = dir.join("assets");
            if candidate.is_dir() {
                return candidate;
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets")
}

pub fn gif_path(name: &str) -> PathBuf { assets_dir().join("gifs").join(name) }
