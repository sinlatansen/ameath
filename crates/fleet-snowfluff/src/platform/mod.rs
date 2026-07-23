//! Per-platform display-priority layering (tasks 7/8/9) behind one trait,
//! per design.md D5's tiered acceptance. Each platform module implements
//! desktop-only placement, fullscreen-hide detection, topmost, and
//! click-through. macOS (8.1-8.3), Windows (7.1/7.2 -- topmost and
//! click-through are handled generically by Tauri on Windows, see
//! `windows.rs`'s module doc), and Linux X11 (9.1/9.2 -- topmost and
//! click-through are generic here too, see `linux.rs`'s module doc) are
//! implemented. Linux is compile/link-verified only via `just build-
//! linux`'s container (this development environment has no X11 display
//! to test real window-manager behavior against, task 9.4).

#[cfg(target_os = "linux")]
pub mod linux;
#[cfg(target_os = "macos")]
pub mod macos;
#[cfg(target_os = "windows")]
pub mod windows;
