#!/usr/bin/env bash
# Rewrites Nix-store-absolute dylib references baked into this
# project's macOS build outputs to their system equivalents.
#
# This repo's .envrc uses `use flake`, so direnv injects the Nix
# devshell into *every* command run in this directory -- including a
# plain `cargo build`/`cargo tauri build` typed directly, no explicit
# `nix develop` needed. That means the linker resolves things like
# `-liconv` against Nix's own copy instead of the system one, baking
# an absolute /nix/store/... path into the binary's load commands.
# That path only exists on machines with this exact Nix store closure,
# so it's not portable -- and worse, once the app is properly signed
# (not ad-hoc), macOS's Library Validation enforces that loaded dylibs
# share the main binary's Team ID or come from a platform path, which
# Nix's copy does neither, so the app fails to even launch (crashes
# with "Library not loaded" at startup instead of a graceful error).
#
# macOS has shipped an ABI-compatible libiconv.2.dylib as part of the
# OS forever (verified against /usr/bin/iconv's own linkage: identical
# compatibility version), so there's nothing to bundle -- just point
# at the system one instead of Nix's.
#
# Runs as tauri's beforeBundleCommand (crates/fleet-snowfluff/
# tauri.conf.json), i.e. after compiling but before the binary is
# copied into the .app and signed -- so tauri-bundler's own signing
# step covers the corrected binary and nothing needs re-signing here.
# No-ops immediately on non-macOS (otool/install_name_tool don't
# exist there), so it's safe to run unconditionally from every
# platform in the CI release matrix.

set -euo pipefail

command -v otool >/dev/null 2>&1 || exit 0
command -v install_name_tool >/dev/null 2>&1 || exit 0

fix_binary() {
    local bin="$1" nix_iconv
    nix_iconv=$(otool -L "$bin" 2>/dev/null | awk '/\/nix\/store\/.*libiconv\.[0-9]+\.dylib/ {print $1}')
    if [[ -n $nix_iconv ]]; then
        echo "fix-macos-dylib-paths: $bin: $nix_iconv -> /usr/lib/libiconv.2.dylib"
        install_name_tool -change "$nix_iconv" /usr/lib/libiconv.2.dylib "$bin"
    fi
}

search_root="${1:-target}"
while IFS= read -r -d '' bin; do
    fix_binary "$bin"
done < <(find "$search_root" -type f -name 'fleet-snowfluff' -perm -u+x -print0 2>/dev/null)
