# Fleet Snowfluff (飞行雪绒)

A cross-platform desktop pet, rewritten in Rust from the original Python
project [Ameath](https://gitee.com/lzy-buaa-jdi/ameath). Fleet Snowfluff
wanders your screen, follows your cursor, and reacts when you drag it —
running natively on **Windows**, **macOS**, and **Ubuntu**.

> **Status:** this repository is mid-rewrite (targeting `v0.1.0`). The
> original Python app still lives at [`legacy/`](legacy/) and remains
> runnable as the behavior reference while the Rust port is built. See
> [`openspec/changes/`](openspec/changes/) for the active change proposal,
> design, and specs.

## Features (target for v0.1.0)

- Motion state machine — wander, follow-mouse, curious, and rest states with
  inertia-based, non-robotic movement
- Draggable with a voice reaction; multiple simultaneous instances (up to 80)
- Adjustable scale, opacity, and display priority (always-on-top, normal
  with auto-hide over fullscreen apps, or desktop-only)
- Click-through, multi-monitor placement, system tray, and a native
  right-click quick menu
- UI in Traditional Chinese, Simplified Chinese, English, Japanese, and
  Korean, detected from the system locale
- Switchable voice-line language (Chinese included at launch; Japanese,
  English, and Korean packs are supported but not yet recorded), plus a
  volume control
- Signed auto-updates via GitHub Releases

The music player from the original Ameath app has been intentionally
dropped from this rewrite.

## Development

Once the Rust workspace is scaffolded (see the change proposal for
progress):

```sh
just dev    # run the app
just build  # produce a release build
just test   # run the core crate's test suite
```

A [Nix devshell](flake.nix) provides the Rust toolchain and formatters; run
`nix develop` or let `direnv` load it automatically.

Always use `just dev`/`just build` (or `cargo tauri dev`/`cargo tauri build`
directly) rather than a plain `cargo run`/`cargo build` — the settings
window is the app's only webview, and a raw cargo invocation doesn't enable
the Tauri CLI's `custom-protocol` feature, so it tries to load the Vite dev
server URL instead of the bundled frontend even when nothing is serving
it, leaving that window silently blank.

## Origins & Attribution

Fleet Snowfluff is a Rust rewrite of **Ameath**, a fan-made desktop pet
originally created by [**-fugu-**](https://space.bilibili.com/84508966).
All character art, animations, and voice clips bundled in this repository
originate from that project. The Rust rewrite (architecture, rendering,
and platform support) is maintained by
[kagetsuki1997](https://github.com/kagetsuki1997).

The pet character and its assets belong to **Wuthering Waves** by
**Kuro Games**. This is an unofficial fan project; it is not affiliated
with or endorsed by Kuro Games. Assets will be removed promptly upon any
legitimate infringement request.

## License

Code is licensed under the [MIT License](LICENSE). Bundled character
assets (GIFs, voice clips) are excluded from that grant — see the
disclaimer above.

## Contributing

Forks, issues, and pull requests are welcome. If you plan to work on an
open issue, please say so first to avoid duplicate effort.
