//! Asset path resolution. In a bundled build, GIFs ship as Tauri
//! resources; in dev, they're read straight from the workspace's
//! `assets/` directory. Bundled-resource wiring lands with the release
//! pipeline (task 16); for now this always resolves the dev path, which
//! is also what CI's headless core tests never touch (only the shell
//! binary does).

use std::path::PathBuf;

pub fn assets_dir() -> PathBuf { PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets") }

pub fn gif_path(name: &str) -> PathBuf { assets_dir().join("gifs").join(name) }
