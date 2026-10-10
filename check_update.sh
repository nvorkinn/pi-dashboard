#!/usr/bin/env bash
# Updates this Pi to the GitHub release marked "latest", if it isn't on it
# already: downloads that release's install.sh and runs it. Releases are built
# as pre-releases; promote one with
#   gh release edit <tag> --prerelease=false --latest
# install.sh installs this script and the timer that runs it (see systemd/).
#
# Usage: sudo check_update.sh
set -euo pipefail

REPO="nvorkinn/pi-dashboard"
STATE_DIR="/etc/pi-setup"
TOKEN_FILE="$STATE_DIR/github-token"
DEVICE_NAME_FILE="$STATE_DIR/device-name"
INSTALLED_TAG_FILE="$STATE_DIR/installed-tag"

# Everything is in main() so bash has parsed the whole script before install.sh
# replaces it on disk.
main() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "This script needs root (install.sh does). Re-run with sudo." >&2
        exit 1
    fi

    exec 9> /run/lock/pi-dashboard-update.lock
    if ! flock -n 9; then
        echo "Another update is already running."
        exit 0
    fi

    [ -f "$TOKEN_FILE" ] || { echo "No $TOKEN_FILE -- run install.sh by hand first." >&2; exit 1; }
    [ -f "$DEVICE_NAME_FILE" ] || { echo "No $DEVICE_NAME_FILE -- run install.sh by hand first." >&2; exit 1; }
    GITHUB_TOKEN="$(cat "$TOKEN_FILE")"
    export GITHUB_TOKEN

    local tag
    tag="$(gh release view --repo "$REPO" --json tagName --jq .tagName)"

    local installed=""
    [ -f "$INSTALLED_TAG_FILE" ] && installed="$(cat "$INSTALLED_TAG_FILE")"
    if [ "$tag" = "$installed" ]; then
        echo "Already on $tag."
        exit 0
    fi
    echo "Latest release is $tag (installed: ${installed:-unknown})."

    # Not local: the EXIT trap runs after main() has returned.
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' EXIT
    gh release download "$tag" --repo "$REPO" --pattern install.sh --dir "$tmp_dir"

    bash "$tmp_dir/install.sh" "$tag" "$(cat "$DEVICE_NAME_FILE")"
}

main "$@"
