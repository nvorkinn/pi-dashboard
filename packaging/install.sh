#!/usr/bin/env bash
# Installs countdown from a GitHub release and sets it up as a systemd service.
#
# countdown is a private repo, so fetching from it needs a token with read
# access, passed via GITHUB_TOKEN. Uses the gh CLI (bootstrapped below if
# missing) to resolve releases and download assets -- gh handles private-repo
# auth correctly on its own; a hand-rolled curl approach needs the asset API
# plus an Accept header, since a private repo's browser_download_url doesn't
# work with a bearer token. Nothing is ever fetched from main -- see
# README.md for the full bootstrap snippet that resolves a tag (specified,
# or latest via the releases API) before the first curl fetches this script
# from that tag.
#
# Usage (once TAG is resolved -- see README.md):
#   curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
#       "https://raw.githubusercontent.com/nvorkinn/countdown/$TAG/packaging/install.sh" \
#       | GITHUB_TOKEN="$GITHUB_TOKEN" sudo -E bash -s -- "$TAG"
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
[ -n "${GITHUB_TOKEN:-}" ] || { echo "GITHUB_TOKEN is required (countdown is a private repo)." >&2; exit 1; }
export GITHUB_TOKEN

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

echo "Installing countdown for user '$TARGET_USER' (app dir: $APP_DIR)..."

if [ "$VERSION" = "latest" ]; then
    TAG="$(gh release view --repo "$REPO" --json tagName --jq .tagName)"
else
    TAG="$VERSION"
fi
echo "Resolved release $TAG"

echo "Downloading release assets..."
gh release download "$TAG" --repo "$REPO" --dir "$TMP_DIR" --clobber \
    --pattern '*.whl' --pattern 'countdown.service'
# uv tool install parses name/version from the wheel filename itself; gh
# preserves the real name (e.g. countdown-0.3.1-py3-none-any.whl).
WHEEL_PATH="$(ls "$TMP_DIR"/*.whl)"
# gh creates these respecting the caller's umask -- when invoked from a
# script that tightened its own umask (e.g. pi-setup, to protect its token/
# key files), that leaks in here too and leaves the wheel unreadable by
# TARGET_USER. Force it open regardless of what we inherited.
chmod 644 "$WHEEL_PATH" "$TMP_DIR/countdown.service"

if ! run_as_target "command -v uv" >/dev/null 2>&1; then
    echo "uv not found for $TARGET_USER, installing it..."
    run_as_target "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

echo "Installing the countdown wheel with uv tool..."
run_as_target "uv tool install --force '$WHEEL_PATH'"

EXEC_START="$(run_as_target "uv tool dir --bin")/countdown"
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
systemctl enable --now countdown.service

echo "Done. countdown.service is running -- check it with:"
echo "  systemctl status countdown"
echo "  journalctl -u countdown -f"
echo "Edit $APP_DIR/config.json then 'systemctl restart countdown' to apply changes."
