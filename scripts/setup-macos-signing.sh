#!/usr/bin/env bash
# Generates and (re)installs the self-signed code-signing identity this
# project uses on macOS -- see commit history around
# tauri.conf.json's bundle.macOS.signingIdentity for the full story.
# Short version: without a paid Apple Developer ID, every macOS build
# gets an ad-hoc signature that changes on every rebuild, which means
# Accessibility (device_query's global mouse polling, needed for drag/
# follow-mouse/right-click) never stays granted past a rebuild. A
# self-signed cert, reused for *every* build (local and CI), gives the
# app a stable identity so the grant survives rebuilds and app updates.
# It does NOT satisfy Gatekeeper for other users downloading a release
# -- that still needs a real Apple Developer ID + notarization.
#
# The cert's Common Name (CERT_CN below) must exactly match
# `bundle.macOS.signingIdentity` in crates/fleet-snowfluff/tauri.conf.json.
#
# Usage:
#   scripts/setup-macos-signing.sh generate       # one-time (or --force to rotate)
#   scripts/setup-macos-signing.sh import         # install into this machine's login keychain
#   scripts/setup-macos-signing.sh push-secrets   # sync APPLE_CERTIFICATE(_PASSWORD) to GitHub Actions
#   scripts/setup-macos-signing.sh all            # generate + import + push-secrets
#
# `generate` only needs to run once, ever -- re-running it (without
# --force) refuses to overwrite an existing cert, since a NEW cert is a
# NEW identity and immediately breaks every Accessibility grant this
# was meant to stabilize (locally and for anyone who already has a
# release built with the old one). Re-running `import`/`push-secrets`
# any time is always safe (both are idempotent).

set -euo pipefail

CERT_CN="Fleet Snowfluff Self-Signed"
GH_REPO="kagetsuki1997/fleet-snowfluff"

# Deliberately outside the repo -- this directory holds a private key
# and its password file; never point it at a path git tracks.
CERT_DIR="${FLEET_SNOWFLUFF_CODESIGN_DIR:-$HOME/.local/share/fleet-snowfluff/codesign}"
KEY_PATH="$CERT_DIR/fleet-snowfluff-codesign.key"
CRT_PATH="$CERT_DIR/fleet-snowfluff-codesign.crt"
P12_PATH="$CERT_DIR/fleet-snowfluff-codesign.p12"
PASSWORD_PATH="$CERT_DIR/p12-password.txt"

cmd_generate() {
    local force="${1:-}"
    if [[ -f $P12_PATH && $force != "--force" ]]; then
        echo "Already exists at $P12_PATH -- pass --force to rotate it." >&2
        echo "Rotating creates a NEW identity and breaks every Accessibility grant" >&2
        echo "this cert was used for, locally and in every released build. Only do" >&2
        echo "this deliberately." >&2
        exit 1
    fi

    mkdir -p "$CERT_DIR"
    chmod 700 "$CERT_DIR"

    openssl req -x509 -newkey rsa:2048 -keyout "$KEY_PATH" -out "$CRT_PATH" \
        -days 7300 -nodes -subj "/CN=$CERT_CN" \
        -addext "keyUsage=critical,digitalSignature" \
        -addext "extendedKeyUsage=critical,codeSigning"

    local password
    password=$(openssl rand -base64 24)
    printf '%s' "$password" >"$PASSWORD_PATH"
    chmod 600 "$KEY_PATH" "$PASSWORD_PATH"

    openssl pkcs12 -export -legacy -out "$P12_PATH" \
        -inkey "$KEY_PATH" -in "$CRT_PATH" -passout "pass:$password"

    echo "Generated $P12_PATH (valid until $(openssl x509 -in "$CRT_PATH" -noout -enddate | cut -d= -f2))."
    echo "Password saved to $PASSWORD_PATH -- consider moving it into a password"
    echo "manager and deleting that file once 'push-secrets' has run."
}

cmd_import() {
    [[ -f $P12_PATH ]] || {
        echo "No cert at $P12_PATH yet -- run 'generate' first." >&2
        exit 1
    }
    local password
    password=$(cat "$PASSWORD_PATH")
    security import "$P12_PATH" -k "$HOME/Library/Keychains/login.keychain-db" \
        -P "$password" -T /usr/bin/codesign -T /usr/bin/security
    echo "Imported into your login keychain."
    echo "One more step, interactively (needs your macOS account password, not the p12 one):"
    echo "  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k <your-login-password> \"$HOME/Library/Keychains/login.keychain-db\""
    echo "Without it, codesign may pop a keychain-access prompt on every build."
}

cmd_push_secrets() {
    [[ -f $P12_PATH ]] || {
        echo "No cert at $P12_PATH yet -- run 'generate' first." >&2
        exit 1
    }
    base64 -i "$P12_PATH" | gh secret set APPLE_CERTIFICATE --repo "$GH_REPO"
    cat "$PASSWORD_PATH" | gh secret set APPLE_CERTIFICATE_PASSWORD --repo "$GH_REPO"
    echo "Pushed APPLE_CERTIFICATE and APPLE_CERTIFICATE_PASSWORD to $GH_REPO."
}

case "${1:-}" in
    generate)
        cmd_generate "${2:-}"
        ;;
    import)
        cmd_import
        ;;
    push-secrets)
        cmd_push_secrets
        ;;
    all)
        cmd_generate "${2:-}"
        cmd_import
        cmd_push_secrets
        ;;
    *)
        echo "Usage: $0 {generate [--force]|import|push-secrets|all}" >&2
        exit 1
        ;;
esac
