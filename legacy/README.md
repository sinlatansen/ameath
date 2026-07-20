# Legacy: Ameath (Python)

This is the original Python/tkinter implementation of the desktop pet, kept
permanently as the behavior reference for the Rust rewrite
([Fleet Snowfluff](../README.md)). It is not shipped as a product; it exists
so the pet's motion and timing "feel" can be compared side-by-side against
the Rust port while that port is being built.

The music player is out of scope for the rewrite (see the change proposal
under `../openspec/`). The bundled MP3s under `../sound/music/` have been
deleted; the `ameath/music_player.py` module and its settings tab remain in
this legacy copy for reference but have no audio files left to play.

## Running

Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
cd legacy
uv run ./main.py
```

## Building the old Windows executable

```sh
cd legacy
uv run pyinstaller ameath.spec --noconfirm
```

Assets referenced by this app (`gifs/`, `sound/voice/`, `fonts/`) live at
the repository root under `../assets/` — see `ameath/constants.py` and
`ameath/utils.py::resource_path` for how paths resolve during development
vs. a packaged build.
