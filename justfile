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

# Builds and runs the Linux target natively inside `docker/linux-build.
# Dockerfile` (Tauri links directly against webkit2gtk/GTK at build
# time, so cross-compiling from macOS isn't practical -- a real Linux
# container sidesteps that). Deliberately does NOT pass `--platform
# linux/amd64`: on Apple Silicon that forces QEMU emulation, which OOM
# killed the `gtk` crate under Docker Desktop's default memory limit.
# Building natively for the host's own arch (aarch64 on Apple Silicon)
# avoids emulation entirely and produces an aarch64 Linux binary --
# fine for local build/lint/test verification, not what CI's
# release.yaml ships (that runs on real x86_64 GitHub runners).
# Volumes cache cargo's registry, the UI's node_modules, and target/
# across runs so repeat builds don't start from scratch.
build-linux:
    docker build -f docker/linux-build.Dockerfile -t fleet-snowfluff-linux-build .
    docker volume create fleet-snowfluff-linux-ui-node-modules >/dev/null
    docker volume create fleet-snowfluff-linux-cargo-registry >/dev/null
    docker volume create fleet-snowfluff-linux-target >/dev/null
    docker run --rm \
        -v "$PWD":/workspace \
        -v fleet-snowfluff-linux-ui-node-modules:/workspace/ui/node_modules \
        -v fleet-snowfluff-linux-cargo-registry:/usr/local/cargo/registry \
        -v fleet-snowfluff-linux-target:/workspace/target \
        -w /workspace \
        fleet-snowfluff-linux-build \
        bash -c "npm ci --prefix ui && cd crates/fleet-snowfluff && tauri build --no-bundle"
    @echo "Built inside the container at target/release/fleet-snowfluff (aarch64 ELF) -- copy out with: docker run --rm -v fleet-snowfluff-linux-target:/t alpine cat /t/release/fleet-snowfluff > fleet-snowfluff-linux"

test:
    cargo test --workspace

lint:
    cargo clippy --workspace --all-targets -- -D warnings

fmt:
    nix develop -c treefmt --allow-missing-formatter --no-cache -C .

# (Re)generates/installs/syncs the self-signed macOS code-signing
# identity -- see scripts/setup-macos-signing.sh's own header for why
# it exists. `just macos-signing generate`, `import`, `push-secrets`,
# or `all`.
macos-signing *args:
    scripts/setup-macos-signing.sh {{ args }}

legacy-dev:
    cd legacy; uv run ./main.py

legacy-build:
    cd legacy; uv run pyinstaller ameath.spec --noconfirm
