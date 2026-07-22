set dotenv-load

default: dev

alias d := dev
alias b := build

dev:
    cd crates/fleet-snowfluff; cargo tauri dev

build:
    cd crates/fleet-snowfluff; cargo tauri build

# Cross-compiles a portable Windows .exe from macOS/Linux via cargo-xwin
# (downloads MSVC headers/libs, links with lld) -- goes through `cargo
# tauri build` rather than plain `cargo build` so custom-protocol gets
# enabled correctly (see settings_window.rs for why that matters) and
# the frontend gets built; --no-bundle skips NSIS/MSI packaging since
# this is just meant to be copied over and run directly, not installed.
# GIFs and voice clips are embedded into the binary itself (assets.rs),
# so the .exe alone is the whole artifact -- nothing else to copy.
build-windows:
    cd crates/fleet-snowfluff && nix develop -c cargo tauri build --target x86_64-pc-windows-msvc --runner cargo-xwin --no-bundle
    @echo "Portable build ready: target/x86_64-pc-windows-msvc/release/fleet-snowfluff.exe -- copy that one file to Windows and run it"

test:
    cargo test --workspace

lint:
    cargo clippy --workspace --all-targets -- -D warnings

fmt:
    nix develop -c treefmt --allow-missing-formatter --no-cache -C .

legacy-dev:
    cd legacy; uv run ./main.py

legacy-build:
    cd legacy; uv run pyinstaller ameath.spec --noconfirm
