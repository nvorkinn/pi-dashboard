#!/usr/bin/env bash
# Installs countdown from a GitHub release and sets it up as a systemd service.
#
# Usage:
#   sudo ./install.sh [version]
#   curl -fsSL https://raw.githubusercontent.com/nvorkinn/countdown/main/packaging/install.sh | sudo bash -s -- [version]
#
# [version] is a release tag such as "v0.3.0". Defaults to the latest release.
#
# Re-running this script (e.g. to update) reinstalls the wheel and restarts
# the service, but never overwrites an existing config.json.
set -euo pipefail

REPO="nvorkinn/countdown"
VERSION="${1:-latest}"
APP_DIR="${COUNTDOWN_APP_DIR:-/opt/countdown}"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root to install the systemd unit. Re-run with sudo." >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-root}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
if [ -z "$TARGET_HOME" ]; then
    echo "Could not resolve a home directory for user '$TARGET_USER'." >&2
    exit 1
fi

run_as_target() {
    sudo -u "$TARGET_USER" -H env HOME="$TARGET_HOME" bash -lc "$1"
}

echo "Installing countdown for user '$TARGET_USER' (app dir: $APP_DIR)..."

if [ "$VERSION" = "latest" ]; then
    RELEASE_URL="https://api.github.com/repos/$REPO/releases/latest"
else
    RELEASE_URL="https://api.github.com/repos/$REPO/releases/tags/$VERSION"
fi

RELEASE_INFO="$(curl -fsSL "$RELEASE_URL" | python3 -c '
import json, sys
release = json.load(sys.stdin)
assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
wheel = next(url for name, url in assets.items() if name.endswith(".whl"))
service = assets["countdown.service"]
print(release["tag_name"], wheel, service)
')"
read -r TAG WHEEL_URL SERVICE_URL <<< "$RELEASE_INFO"

if [ -z "$TAG" ] || [ -z "$WHEEL_URL" ] || [ -z "$SERVICE_URL" ]; then
    echo "Could not find a wheel and countdown.service asset on release '$VERSION'." >&2
    exit 1
fi

echo "Resolved release $TAG"

if ! run_as_target "command -v uv" >/dev/null 2>&1; then
    echo "uv not found for $TARGET_USER, installing it..."
    run_as_target "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

echo "Installing the countdown wheel with uv tool..."
run_as_target "uv tool install --force '$WHEEL_URL'"

EXEC_START="$(run_as_target "uv tool dir --bin")/countdown"
if [ ! -e "$EXEC_START" ]; then
    echo "Expected countdown executable at $EXEC_START but it's missing." >&2
    exit 1
fi

mkdir -p "$APP_DIR"
chown "$TARGET_USER" "$APP_DIR"

if [ ! -f "$APP_DIR/config.json" ]; then
    echo "Seeding $APP_DIR/config.json from config.example.json..."
    curl -fsSL "https://raw.githubusercontent.com/$REPO/$TAG/config.example.json" -o "$APP_DIR/config.json"
    chown "$TARGET_USER" "$APP_DIR/config.json"
else
    echo "Keeping existing $APP_DIR/config.json."
fi

echo "Installing systemd unit..."
SERVICE_FILE="$(mktemp)"
trap 'rm -f "$SERVICE_FILE"' EXIT
curl -fsSL "$SERVICE_URL" -o "$SERVICE_FILE"
sed \
    -e "s#@USER@#$TARGET_USER#" \
    -e "s#@WORKING_DIRECTORY@#$APP_DIR#" \
    -e "s#@EXEC_START@#$EXEC_START#" \
    "$SERVICE_FILE" > /etc/systemd/system/countdown.service

systemctl daemon-reload
systemctl enable --now countdown.service

echo "Done. countdown.service is running -- check it with:"
echo "  systemctl status countdown"
echo "  journalctl -u countdown -f"
echo "Edit $APP_DIR/config.json then 'systemctl restart countdown' to apply changes."
