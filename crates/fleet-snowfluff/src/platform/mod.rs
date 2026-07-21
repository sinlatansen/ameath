//! Per-platform display-priority layering (tasks 7/8/9) behind one trait,
//! per design.md D5's tiered acceptance. Each platform module implements
//! desktop-only placement, fullscreen-hide detection, topmost, and
//! click-through; only macOS is implemented so far (tasks 8.1-8.3) since
//! it's the one platform this development environment can verify.

#[cfg(target_os = "macos")]
pub mod macos;
