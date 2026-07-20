//! Pure positioning math for pause-mode window docking (D15): given the
//! rect of an eligible foreground window, compute where the pet should
//! sit, or `None` if it shouldn't dock at all. Ported from legacy's
//! docking offset (`pet.py`'s `move()` window-snap branch), but decoupled
//! from *which* window is eligible — legacy matched a hardcoded app
//! allowlist; this rewrite docks to whatever window is currently
//! foreground, so eligibility (normal window state, not desktop/shell,
//! not the pet's own window) is decided by the platform-specific caller
//! before it ever reaches this function.

use crate::motion::{Bounds, PetSize};

/// A foreign window's rect in the same coordinate space as `Bounds`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ForeignWindowRect {
    pub left: f64,
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
}

/// Computes the dock position (pet anchored to the window's top-right
/// corner) if `window` is present and the resulting position fits within
/// `bounds`. Returns `None` when there's no eligible window or the
/// computed position would fall outside `bounds` (matching legacy, which
/// silently declines to dock rather than clamping into range).
pub fn compute_dock_position(
    window: Option<ForeignWindowRect>,
    bounds: Bounds,
    size: PetSize,
) -> Option<(f64, f64)> {
    let window = window?;
    let pet_x = window.right - size.w;
    let pet_y = window.top - size.h + 5.0;

    let fits = pet_x > bounds.left
        && pet_x < bounds.right - size.w
        && pet_y > bounds.top
        && pet_y < bounds.bottom - size.h;

    fits.then_some((pet_x, pet_y))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bounds() -> Bounds { Bounds { left: 0.0, top: 0.0, right: 1920.0, bottom: 1080.0 } }
    fn size() -> PetSize { PetSize { w: 200.0, h: 200.0 } }

    #[test]
    fn no_window_means_no_dock() {
        assert_eq!(compute_dock_position(None, bounds(), size()), None);
    }

    #[test]
    fn dock_position_matches_legacy_offset() {
        let window = ForeignWindowRect { left: 100.0, top: 300.0, right: 900.0, bottom: 700.0 };
        let pos = compute_dock_position(Some(window), bounds(), size()).unwrap();
        assert_eq!(pos.0, window.right - size().w);
        assert_eq!(pos.1, window.top - size().h + 5.0);
    }

    #[test]
    fn declines_to_dock_when_position_falls_outside_bounds() {
        // Window near the very top edge pushes pet_y above bounds.top.
        let window = ForeignWindowRect { left: 100.0, top: 10.0, right: 900.0, bottom: 700.0 };
        assert_eq!(compute_dock_position(Some(window), bounds(), size()), None);
    }
}
