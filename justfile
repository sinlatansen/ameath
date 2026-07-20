set shell := ["nu", "-c"]

default: dev

alias d := dev
alias b := build

dev:
    cd crates/fleet-snowfluff; cargo tauri dev

build:
    cd crates/fleet-snowfluff; cargo tauri build

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
