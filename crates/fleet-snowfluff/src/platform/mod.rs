//! Per-platform display-priority layering (tasks 7/8/9) behind one trait,
//! per design.md D5's tiered acceptance. Each platform module implements
//! desktop-only placement, fullscreen-hide detection, topmost, and
//! click-through. macOS (8.1-8.3) and Windows (7.1/7.2 -- topmost and
//! click-through are handled generically by Tauri on Windows, see
//! `windows.rs`'s module doc) are implemented; Linux X11 (group 9)
//! isn't, since this development environment can't verify it.

#[cfg(target_os = "macos")]
pub mod macos;
#[cfg(target_os = "windows")]
pub mod windows;
