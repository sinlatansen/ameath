# Manual smoke-test checklist

Run this against the built release artifact (not `just dev`) before publishing a
draft GitHub Release. Copy this file's checkbox list into the release's tracking
issue/PR per version, since results are per-build, not permanent. Acceptance bar
per platform is per design.md D5: Windows is strict parity with legacy Ameath,
macOS and Linux (GNOME/KDE X11) are verified-but-not-pixel-identical; other
Linux WMs are best-effort, not release blockers.

## Version: \_\_\_\_ (fill in before running)

## All platforms

- [ ] Fresh install (no prior config file): app starts with default settings,
      one pet visible, no crash or blank window
- [ ] Legacy-config migration: with `%APPDATA%/ameath_config.json` (or the
      platform-equivalent legacy path) present, first launch migrates settings,
      leaves the legacy file untouched, and removes the legacy autostart
      registration
- [ ] All settings-window controls (scale, opacity, display priority, wander
      mode, monitor select, window snap, instance count, autostart, UI
      language, voice enable/volume/language) apply live and persist across
      restart
- [ ] Settings window opens from tray, from the pet's right-click quick menu,
      and (when an update is pending) from the startup update check -- always
      exactly one window, never a second instance
- [ ] Voice: all four languages (zh/ja/en/ko) play distinct clips on drag
      start, respecting the anti-repeat rule (no clip 3x consecutively) and the
      volume/enable settings
- [ ] UI language switch updates both the settings webview and the native
      title bar without restart
- [ ] Multi-instance: raising/lowering instance count spawns/tears down pets
      immediately, all sharing the same settings
- [ ] Update flow (against a test release with a real newer version
      published): startup check finds it, settings opens on the update tab,
      manual check-for-updates works independent of startup, install-and-
      restart succeeds, skip-this-version and skip-all-updates both suppress
      future prompts as expected
- [ ] Quitting from the tray or quick menu exits cleanly, no orphaned pet
      windows or processes left behind

## Windows (strict parity)

- [ ] Display priority 1 (topmost): pet stays above all normal windows
- [ ] Display priority 2 (normal): pet auto-hides when a fullscreen app is in
      the foreground, reappears when it exits fullscreen
- [ ] Display priority 3 (desktop-only): pet attaches behind desktop icons via
      WorkerW, stays visible with no app maximized, and doesn't come forward
      over any other window
- [ ] Click-through toggle: mouse events pass through to whatever's behind the
      pet when enabled
- [ ] Window-snap docking: while paused, pet snaps to the current foreground
      window's top-right corner (correct position across differently-DPI-
      scaled monitors), releases back to its resting position when that window
      closes or the pet unpauses
- [ ] NSIS installer: install, launch from Start Menu, uninstall cleanly
      (no leftover registry autostart entry, no leftover files outside user
      config)
- [ ] Autostart: enabling it in settings creates a real login item; disabling
      removes it; matches on next launch even if changed outside the app

## macOS (verified)

- [ ] Display priority 1/2/3 behave analogously to Windows (topmost / normal
      with fullscreen-hide / desktop-level via `kCGDesktopWindowLevel`)
- [ ] Click-through toggle ignores mouse events correctly
- [ ] Window-snap docking works using `CGWindowListCopyWindowInfo`-sourced
      window rects
- [ ] `.dmg` installs the universal binary; runs on both Apple Silicon and
      Intel without Rosetta-related surprises
- [ ] Accessibility/Input Monitoring permission prompt appears once on first
      launch (for drag/follow-mouse global mouse polling) and isn't required
      to re-grant on every subsequent launch of a signed release build
- [ ] Autostart login item registers/deregisters correctly via System
      Settings > General > Login Items

## Linux X11 (verified: GNOME, KDE)

- [ ] Display priority 1/2/3 via `_NET_WM_STATE_ABOVE` /
      `_NET_WM_STATE_FULLSCREEN` detection / `_NET_WM_WINDOW_TYPE_DESKTOP`
- [ ] Click-through toggle works on both GNOME and KDE
- [ ] Window-snap docking works on both GNOME and KDE
- [ ] `.deb` installs and launches from the applications menu; AppImage runs
      standalone with executable bit set, no install step
- [ ] Autostart entry (`~/.config/autostart/`) registers/deregisters correctly
- [ ] XWayland: note whether the app runs at all under Wayland sessions via
      XWayland and whether desktop-only/fullscreen-hide degrade gracefully
      (best-effort, not a release blocker -- record the result, don't block on
      it)
- [ ] Other window managers (i3, Xfce, etc.): best-effort only -- note any
      total breakage (crash, window never appears) as a real bug, but visual
      layering quirks are expected and not blocking
