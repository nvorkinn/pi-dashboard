#!/usr/bin/env bash
# Installs countdown from a GitHub release and sets it up as a systemd service.
# See README.md for how to fetch and run it.
#
# Usage: install.sh [version]   (a repo-wide release tag such as "v0.3.0"; defaults to latest)
#
# Re-running it (e.g. to update) never touches APP_DIR, so .auth_broker_device survives.
set -euo pipefail

REPO="nvorkinn/pi-dashboard"
VERSION="${1:-latest}"
APP_DIR="${COUNTDOWN_APP_DIR:-/opt/countdown}"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root to install the systemd unit. Re-run with sudo." >&2
    exit 1
fi
[ -n "${GITHUB_TOKEN:-}" ] || { echo "GITHUB_TOKEN is required (pi-dashboard is a private repo)." >&2; exit 1; }
export GITHUB_TOKEN

# SPI only works after a reboot (it's a device-tree overlay), so if it's switched on
# here, the service isn't started until then.
NEED_REBOOT=0
if command -v raspi-config >/dev/null 2>&1; then
    if ! raspi-config nonint get_spi; then
        echo "Enabling SPI via raspi-config (needs a reboot to take effect)..."
        raspi-config nonint do_spi 0
        NEED_REBOOT=1
    fi
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

TMP_DIR="$(mktemp -d)"
chmod 755 "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

if ! command -v gh >/dev/null 2>&1; then
    echo "Installing gh..."
    GH_TAG="$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
    GH_VERSION="${GH_TAG#v}"
    curl -fsSL "https://github.com/cli/cli/releases/download/$GH_TAG/gh_${GH_VERSION}_linux_arm64.tar.gz" \
        | tar -xz -C "$TMP_DIR"
    install -m 755 "$TMP_DIR/gh_${GH_VERSION}_linux_arm64/bin/gh" /usr/local/bin/gh
fi

# libfribidi0 turns on Pillow's Raqm text layout, so the Pi lays out text exactly
# like the tests' golden images.
echo "Installing system dependencies..."
apt-get update && apt-get install -y --no-install-recommends swig liblgpio-dev libfribidi0

echo "Installing countdown for user '$TARGET_USER' (app dir: $APP_DIR)..."

if [ "$VERSION" = "latest" ]; then
    TAG="$(gh release view --repo "$REPO" --json tagName --jq .tagName)"
else
    TAG="$VERSION"
fi
echo "Resolved release $TAG"

echo "Downloading release assets..."
gh release download "$TAG" --repo "$REPO" --dir "$TMP_DIR" --clobber \
    --pattern 'countdown_core-*.whl' --pattern 'countdown_standalone-*.whl' --pattern 'countdown.service'
# uv tool install parses name/version from the wheel filename, which gh preserves.
CORE_WHEEL="$(ls "$TMP_DIR"/countdown_core-*.whl)"
STANDALONE_WHEEL="$(ls "$TMP_DIR"/countdown_standalone-*.whl)"
# The repo-root install.sh runs with umask 077, which would leave these unreadable
# by TARGET_USER.
chmod 644 "$CORE_WHEEL" "$STANDALONE_WHEEL" "$TMP_DIR/countdown.service"

if ! run_as_target "command -v uv" >/dev/null 2>&1; then
    echo "uv not found for $TARGET_USER, installing it..."
    run_as_target "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

echo "Installing the countdown wheels with uv tool..."
# countdown-core isn't on an index, so its wheel (from the same release) is handed over alongside.
run_as_target "uv tool install --force '$STANDALONE_WHEEL' --with '$CORE_WHEEL'"
# Releases before the core/standalone split installed a tool called just "countdown".
run_as_target "uv tool uninstall countdown" >/dev/null 2>&1 || true

EXEC_START="$(run_as_target "uv tool dir --bin")/countdown-standalone"
if [ ! -e "$EXEC_START" ]; then
    echo "Expected countdown executable at $EXEC_START but it's missing." >&2
    exit 1
fi

mkdir -p "$APP_DIR"
chown "$TARGET_USER" "$APP_DIR"

echo "Installing systemd unit..."
sed \
    -e "s#@USER@#$TARGET_USER#" \
    -e "s#@WORKING_DIRECTORY@#$APP_DIR#" \
    -e "s#@EXEC_START@#$EXEC_START#" \
    "$TMP_DIR/countdown.service" > /etc/systemd/system/countdown.service

systemctl daemon-reload

# Only this service start's logs, not earlier runs'.
LOG_CMD='journalctl _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID --value countdown) -f'

if [ "$NEED_REBOOT" -eq 1 ]; then
    systemctl enable countdown.service
    echo "Done. countdown.service is installed and enabled, but SPI was just turned on and"
    echo "needs a reboot before the display hardware works. Reboot now with:"
    echo "  sudo reboot"
    echo "It will start automatically on boot. After that, check it with:"
    echo "  systemctl status countdown"
    echo "  $LOG_CMD"
else
    # restart, not `enable --now`, which is a no-op for a running service (an update).
    systemctl enable countdown.service
    systemctl restart countdown.service
    echo "Done. countdown.service is running -- check it with:"
    echo "  systemctl status countdown"
    echo "  $LOG_CMD"
fi
echo "On first run it'll register with auth-broker and show a pairing code on the"
echo "display -- go to https://nikolaivorkinn.com and enter it to finish setup."
