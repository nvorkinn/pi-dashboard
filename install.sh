#!/usr/bin/env bash
# Provisions a Pi with both countdown and pi-telemetry: decrypts each app's
# secrets from this repo and installs both apps via their own installers,
# each set up as its own systemd unit.
#
# This repo is private, so every fetch here (including fetching this script
# itself) needs a GitHub token with read access to it. See README.md for how
# to create one and for the age private key this script asks for on first
# run.
#
# Uses the gh CLI (bootstrapped below if missing) to resolve releases and
# download assets -- gh handles private-repo auth correctly on its own,
# where a hand-rolled curl approach needs the asset API plus an Accept
# header (browser_download_url doesn't work with a bearer token on a
# private repo), and gh also preserves each asset's real filename.
#
# Nothing here is ever fetched from a branch (main included) -- everything
# is pinned to one tagged release. countdown and pi-telemetry are released
# together under a single tag, and this script installs exactly the tag it
# was fetched from, so the tag you pass is the only version you choose --
# look it up by hand at https://github.com/nvorkinn/pi-dashboard/releases.
#
# Usage:
#   curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
#       "https://raw.githubusercontent.com/nvorkinn/pi-dashboard/<tag>/install.sh" \
#       | sudo -E env GITHUB_TOKEN="$GITHUB_TOKEN" bash -s -- \
#           <tag> <device name>
#
# <device name> is required and identifies this Pi to Home Assistant -- pick
# something that says whose it is (e.g. "sister-hat"). It's sanitized to
# [a-z0-9_-] and written as DEVICE_ID into both apps' env files, so their MQTT
# topics and HA device line up. See README.md.
#
# Re-running with a newer tag updates both apps in place. The GitHub token and
# age private key are cached under /etc/pi-setup after the first run, but
# GITHUB_TOKEN still needs to be in your environment for the outer `curl`
# every time -- that fetch happens before this script (and its cache) exists.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root (it installs systemd units). Re-run with sudo." >&2
    exit 1
fi

TAG="${1:?TAG is required -- pass the exact tag this script was fetched from}"
DEVICE_NAME="${2:?device name is required -- pass it as the second argument (e.g. \"sister-hat\")}"

# Same rules as pi-telemetry's device_id.rs: trim, lowercase, and replace
# anything outside [a-z0-9_-] with "-", so the id is safe as an MQTT topic
# level and client id suffix.
DEVICE_ID="$(printf '%s' "$DEVICE_NAME" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')"
if [ -z "$(printf '%s' "$DEVICE_ID" | tr -d '-')" ]; then
    echo "Device name \"$DEVICE_NAME\" has no usable characters (need at least one of a-z, 0-9, _)." >&2
    exit 1
fi

REPO="nvorkinn/pi-dashboard"
TELEMETRY_ASSET="pi-telemetry-aarch64-unknown-linux-gnu"

export COUNTDOWN_APP_DIR="${COUNTDOWN_APP_DIR:-/opt/countdown}"
TELEMETRY_ENV_FILE="/etc/pi-telemetry/env"

STATE_DIR="/etc/pi-setup"
TOKEN_FILE="$STATE_DIR/github-token"
KEY_FILE="$STATE_DIR/age-key.txt"
DEVICE_ID_FILE="$STATE_DIR/device-id"

umask 077
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

TMP_DIR="$(mktemp -d)"
chmod 755 "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

if [ -f "$DEVICE_ID_FILE" ] && [ "$(cat "$DEVICE_ID_FILE")" != "$DEVICE_ID" ]; then
    echo "Warning: changing device id from \"$(cat "$DEVICE_ID_FILE")\" to \"$DEVICE_ID\"." >&2
    echo "         Home Assistant will treat this as a new device; the old one's entities are orphaned." >&2
fi
echo "$DEVICE_ID" > "$DEVICE_ID_FILE"
echo "Device id: $DEVICE_ID"

if [ -n "${GITHUB_TOKEN:-}" ]; then
    :
elif [ -f "$TOKEN_FILE" ]; then
    GITHUB_TOKEN="$(cat "$TOKEN_FILE")"
else
    echo "Paste a GitHub token with read access to $REPO:"
    read -rs GITHUB_TOKEN < /dev/tty
    echo
fi
[ -n "${GITHUB_TOKEN:-}" ] || { echo "A GitHub token is required." >&2; exit 1; }
echo -n "$GITHUB_TOKEN" > "$TOKEN_FILE"
export GITHUB_TOKEN

if [ -f "$KEY_FILE" ]; then
    :
else
    echo "Paste the age private key (AGE-SECRET-KEY-1...):"
    read -rs AGE_KEY < /dev/tty
    echo
    [ -n "$AGE_KEY" ] || { echo "An age private key is required." >&2; exit 1; }
    echo "$AGE_KEY" > "$KEY_FILE"
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "Installing gh..."
    GH_TAG="$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
    GH_VERSION="${GH_TAG#v}"
    curl -fsSL "https://github.com/cli/cli/releases/download/$GH_TAG/gh_${GH_VERSION}_linux_arm64.tar.gz" \
        | tar -xz -C "$TMP_DIR"
    install -m 755 "$TMP_DIR/gh_${GH_VERSION}_linux_arm64/bin/gh" /usr/local/bin/gh
fi

if ! command -v age >/dev/null 2>&1; then
    echo "Installing age..."
    AGE_TAG="$(curl -fsSL https://api.github.com/repos/FiloSottile/age/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
    curl -fsSL "https://github.com/FiloSottile/age/releases/download/$AGE_TAG/age-$AGE_TAG-linux-arm64.tar.gz" \
        | tar -xz -C "$TMP_DIR"
    install -m 755 "$TMP_DIR/age/age" /usr/local/bin/age
fi

echo "Fetching release contents ($TAG)..."
gh release download "$TAG" --repo "$REPO" --dir "$TMP_DIR" --clobber --pattern 'secrets.zip'
unzip -q "$TMP_DIR/secrets.zip" -d "$TMP_DIR/bundle"

# Both apps' installers, systemd units and env templates come from the source
# archive at the tag; the built artifacts (wheel, binary) are release assets.
echo "Fetching source at $TAG..."
mkdir -p "$TMP_DIR/src-archive" "$TMP_DIR/src"
gh release download "$TAG" --repo "$REPO" --archive tar.gz \
    --dir "$TMP_DIR/src-archive" --clobber
tar -xzf "$TMP_DIR"/src-archive/*.tar.gz -C "$TMP_DIR/src" --strip-components=1

# Decrypts secrets/<name>.age from the secrets bundle just downloaded, or
# returns 1 if that file doesn't exist yet (e.g. no real secrets have been
# encrypted for an app yet) -- callers fall back to that app's own defaults.
fetch_secret() {
    local name="$1" out_file="$2"
    local src="$TMP_DIR/bundle/secrets/$name.age"
    if [ -f "$src" ]; then
        age -d -i "$KEY_FILE" "$src" > "$out_file"
        return 0
    fi
    return 1
}

# Sets DEVICE_ID=<id> in an env file, replacing any existing DEVICE_ID line
# (the name passed to this script always wins). Edits in place so an existing
# file keeps its owner and mode; a missing file is created chmod 600, owned by
# the invoking user.
set_device_id() {
    local file="$1" tmp="$TMP_DIR/env.tmp"
    if [ -f "$file" ]; then
        grep -v '^DEVICE_ID=' "$file" > "$tmp" || true
        if [ -s "$tmp" ] && [ -n "$(tail -c1 "$tmp")" ]; then
            echo >> "$tmp"
        fi
    else
        : > "$tmp"
    fi
    echo "DEVICE_ID=$DEVICE_ID" >> "$tmp"
    if [ -f "$file" ]; then
        cat "$tmp" > "$file"
    else
        install -o "${SUDO_USER:-root}" -m 600 "$tmp" "$file"
    fi
}

echo
echo "== countdown =="
mkdir -p "$COUNTDOWN_APP_DIR"
if fetch_secret countdown.env "$COUNTDOWN_APP_DIR/.env"; then
    chmod 600 "$COUNTDOWN_APP_DIR/.env"
    chown "${SUDO_USER:-root}" "$COUNTDOWN_APP_DIR/.env"
else
    echo "No secrets/countdown.env.age in this release -- countdown will start with defaults."
fi

set_device_id "$COUNTDOWN_APP_DIR/.env"

# countdown's installer downloads its own wheel and unit file from the same
# release.
GITHUB_TOKEN="$GITHUB_TOKEN" bash "$TMP_DIR/src/countdown/packaging/install.sh" "$TAG"

echo
echo "== pi-telemetry =="
TELEMETRY_SRC="$TMP_DIR/src/pi-telemetry"
TELEMETRY_USER="$(grep -m1 '^User=' "$TELEMETRY_SRC/systemd/pi-telemetry.service" | cut -d= -f2)"
mkdir -p "$(dirname "$TELEMETRY_ENV_FILE")"
if [ -f "$TELEMETRY_ENV_FILE" ]; then
    echo "Keeping existing $TELEMETRY_ENV_FILE."
elif fetch_secret pi-telemetry.env "$TELEMETRY_ENV_FILE"; then
    chmod 600 "$TELEMETRY_ENV_FILE"
    chown "$TELEMETRY_USER" "$TELEMETRY_ENV_FILE"
else
    echo "No secrets/pi-telemetry.env.age in this release -- its own installer will seed a placeholder env for you to edit."
fi

echo "Fetching pi-telemetry binary..."
gh release download "$TAG" --repo "$REPO" --pattern "$TELEMETRY_ASSET" \
    --dir "$TMP_DIR" --clobber
chmod +x "$TMP_DIR/$TELEMETRY_ASSET"

(cd "$TELEMETRY_SRC" && bash install.sh "$TMP_DIR/$TELEMETRY_ASSET")

# After its installer, so the env file exists whichever way it got there
# (decrypted secret, an existing one kept, or its own seeded placeholder).
# The timer-triggered service re-reads it on its next run.
set_device_id "$TELEMETRY_ENV_FILE"

echo
echo "Done. countdown and pi-telemetry are both installed."
echo "  systemctl status countdown"
echo "  systemctl status pi-telemetry.timer"
