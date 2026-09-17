#!/usr/bin/env bash
# Provisions a Pi with both countdown and pi-telemetry: decrypts each app's
# secrets from this repo and installs both apps via their own installers,
# each set up as its own systemd unit.
#
# countdown and pi-telemetry are private GitHub repos, so every fetch from
# them (including fetching this script itself) needs a GitHub token with
# read access to both. See README.md for how to create one and for the
# age private key this script asks for on first run.
#
# Usage:
#   export GITHUB_TOKEN=ghp_...
#   curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
#       https://raw.githubusercontent.com/nvorkinn/pi-setup/main/install.sh \
#       | sudo -E env GITHUB_TOKEN="$GITHUB_TOKEN" bash -s -- [countdown_version] [pi_telemetry_version]
#
# Each version arg is a release tag (e.g. "v0.3.0"). Both default to "latest".
# Re-running this script updates both apps in place. The GitHub token and
# age private key are cached under /etc/pi-setup after the first run, but
# GITHUB_TOKEN still needs to be in your environment for the outer `curl`
# every time -- that fetch happens before this script (and its cache) exists.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root (it installs systemd units). Re-run with sudo." >&2
    exit 1
fi

COUNTDOWN_VERSION="${1:-latest}"
TELEMETRY_VERSION="${2:-latest}"

COUNTDOWN_REPO="nvorkinn/countdown"
TELEMETRY_REPO="nvorkinn/pi-telemetry"
PISETUP_REPO="nvorkinn/pi-setup"
TELEMETRY_ASSET="pi-telemetry-aarch64-unknown-linux-gnu"

export COUNTDOWN_APP_DIR="${COUNTDOWN_APP_DIR:-/opt/countdown}"
TELEMETRY_ENV_FILE="/etc/pi-telemetry/env"

STATE_DIR="/etc/pi-setup"
TOKEN_FILE="$STATE_DIR/github-token"
KEY_FILE="$STATE_DIR/age-key.txt"

umask 077
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [ -n "${GITHUB_TOKEN:-}" ]; then
    :
elif [ -f "$TOKEN_FILE" ]; then
    GITHUB_TOKEN="$(cat "$TOKEN_FILE")"
else
    echo "Paste a GitHub token with read access to countdown + pi-telemetry:"
    read -rs GITHUB_TOKEN < /dev/tty
    echo
fi
[ -n "${GITHUB_TOKEN:-}" ] || { echo "A GitHub token is required." >&2; exit 1; }
echo -n "$GITHUB_TOKEN" > "$TOKEN_FILE"

if [ -f "$KEY_FILE" ]; then
    :
else
    echo "Paste the age private key (AGE-SECRET-KEY-1...):"
    read -rs AGE_KEY < /dev/tty
    echo
    [ -n "$AGE_KEY" ] || { echo "An age private key is required." >&2; exit 1; }
    echo "$AGE_KEY" > "$KEY_FILE"
fi

gh_curl() {
    curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" "$@"
}

# Downloads a release asset from a private repo. A plain browser_download_url
# doesn't work with a bearer token there -- the asset API endpoint plus an
# Accept header does.
download_asset() {
    local asset_api_url="$1" out_file="$2"
    curl -fsSL -L \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/octet-stream" \
        "$asset_api_url" -o "$out_file"
}

release_json() {
    local repo="$1" version="$2"
    if [ "$version" = "latest" ]; then
        gh_curl "https://api.github.com/repos/$repo/releases/latest"
    else
        gh_curl "https://api.github.com/repos/$repo/releases/tags/$version"
    fi
}

# Decrypts secrets/<name>.age from this repo to $2, or returns 1 if that
# file doesn't exist yet (e.g. no real secrets have been encrypted for an
# app yet) -- callers fall back to that app's own defaults in that case.
fetch_secret() {
    local name="$1" out_file="$2"
    if gh_curl -o "$TMP_DIR/$name.age" "https://raw.githubusercontent.com/$PISETUP_REPO/main/secrets/$name.age"; then
        age -d -i "$KEY_FILE" "$TMP_DIR/$name.age" > "$out_file"
        return 0
    fi
    return 1
}

if ! command -v age >/dev/null 2>&1; then
    echo "Installing age..."
    AGE_TAG="$(curl -fsSL https://api.github.com/repos/FiloSottile/age/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
    curl -fsSL "https://github.com/FiloSottile/age/releases/download/$AGE_TAG/age-$AGE_TAG-linux-arm64.tar.gz" \
        | tar -xz -C "$TMP_DIR"
    install -m 755 "$TMP_DIR/age/age" /usr/local/bin/age
fi

echo
echo "== countdown =="
COUNTDOWN_TAG="$(release_json "$COUNTDOWN_REPO" "$COUNTDOWN_VERSION" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"

mkdir -p "$COUNTDOWN_APP_DIR"
if fetch_secret countdown.env "$COUNTDOWN_APP_DIR/.env"; then
    chmod 600 "$COUNTDOWN_APP_DIR/.env"
    chown "${SUDO_USER:-root}" "$COUNTDOWN_APP_DIR/.env"
else
    echo "No secrets/countdown.env.age in pi-setup yet -- countdown will start with defaults."
fi

gh_curl "https://raw.githubusercontent.com/$COUNTDOWN_REPO/$COUNTDOWN_TAG/packaging/install.sh" \
    | GITHUB_TOKEN="$GITHUB_TOKEN" bash -s -- "$COUNTDOWN_TAG"

echo
echo "== pi-telemetry =="
TELEMETRY_INFO="$(release_json "$TELEMETRY_REPO" "$TELEMETRY_VERSION" | python3 -c '
import json, sys
release = json.load(sys.stdin)
assets = {a["name"]: a["url"] for a in release["assets"]}
print(release["tag_name"], assets["'"$TELEMETRY_ASSET"'"])
')"
read -r TELEMETRY_TAG TELEMETRY_ASSET_API_URL <<< "$TELEMETRY_INFO"

echo "Fetching pi-telemetry source at $TELEMETRY_TAG..."
mkdir -p "$TMP_DIR/telemetry-src"
gh_curl -L "https://github.com/$TELEMETRY_REPO/archive/refs/tags/$TELEMETRY_TAG.tar.gz" \
    | tar -xz -C "$TMP_DIR/telemetry-src" --strip-components=1

TELEMETRY_USER="$(grep -m1 '^User=' "$TMP_DIR/telemetry-src/systemd/pi-telemetry.service" | cut -d= -f2)"
mkdir -p "$(dirname "$TELEMETRY_ENV_FILE")"
if [ -f "$TELEMETRY_ENV_FILE" ]; then
    echo "Keeping existing $TELEMETRY_ENV_FILE."
elif fetch_secret pi-telemetry.env "$TELEMETRY_ENV_FILE"; then
    chmod 600 "$TELEMETRY_ENV_FILE"
    chown "$TELEMETRY_USER" "$TELEMETRY_ENV_FILE"
else
    echo "No secrets/pi-telemetry.env.age in pi-setup yet -- its own installer will seed a placeholder env for you to edit."
fi

echo "Fetching pi-telemetry binary..."
download_asset "$TELEMETRY_ASSET_API_URL" "$TMP_DIR/pi-telemetry"
chmod +x "$TMP_DIR/pi-telemetry"

(cd "$TMP_DIR/telemetry-src" && bash install.sh "$TMP_DIR/pi-telemetry")

echo
echo "Done. countdown and pi-telemetry are both installed."
echo "  systemctl status countdown"
echo "  systemctl status pi-telemetry.timer"
