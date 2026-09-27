#!/usr/bin/env bash
# Updates this Pi to the newest "*-stable" release, if it isn't on it already:
# fetches the repo's tags, picks the most recently created one ending in
# "-stable", downloads that release's install.sh and runs it. install.sh
# installs this script and the timer that runs it (see systemd/).
#
# Usage: sudo check_update.sh
set -euo pipefail

REPO="nvorkinn/pi-dashboard"
STATE_DIR="/etc/pi-setup"
TOKEN_FILE="$STATE_DIR/github-token"
DEVICE_ID_FILE="$STATE_DIR/device-id"
INSTALLED_TAG_FILE="$STATE_DIR/installed-tag"
TAGS_REPO="/var/cache/pi-dashboard/tags.git"

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
    [ -f "$DEVICE_ID_FILE" ] || { echo "No $DEVICE_ID_FILE -- run install.sh by hand first." >&2; exit 1; }
    GITHUB_TOKEN="$(cat "$TOKEN_FILE")"
    export GITHUB_TOKEN

    local tag
    tag="$(newest_stable_tag)"
    if [ -z "$tag" ]; then
        echo "No -stable tags yet."
        exit 0
    fi

    local installed=""
    [ -f "$INSTALLED_TAG_FILE" ] && installed="$(cat "$INSTALLED_TAG_FILE")"
    if [ "$tag" = "$installed" ]; then
        echo "Already on $tag."
        exit 0
    fi
    echo "Newest stable release is $tag (installed: ${installed:-unknown})."

    # The release is built a few minutes after the tag is pushed.
    if ! gh release view "$tag" --repo "$REPO" --json tagName > /dev/null; then
        echo "No release for $tag yet -- will try again next time."
        exit 0
    fi

    # Not local: the EXIT trap runs after main() has returned.
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' EXIT
    gh release download "$tag" --repo "$REPO" --pattern install.sh --dir "$tmp_dir"

    bash "$tmp_dir/install.sh" "$tag" "$(cat "$DEVICE_ID_FILE")"
}

# Prints the most recently created "*-stable" tag (tagger date for annotated
# tags, commit date for lightweight ones), or nothing if there are none.
newest_stable_tag() {
    if [ ! -d "$TAGS_REPO" ]; then
        mkdir -p "$(dirname "$TAGS_REPO")"
        git init -q --bare "$TAGS_REPO"
    fi

    # The token goes in via the environment rather than argv, so other users
    # can't read it from the process list.
    GIT_CONFIG_COUNT=1 \
        GIT_CONFIG_KEY_0=http.extraHeader \
        GIT_CONFIG_VALUE_0="Authorization: Basic $(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)" \
        git -C "$TAGS_REPO" fetch -q --prune --force --no-tags --depth=1 \
        "https://github.com/$REPO.git" '+refs/tags/*-stable:refs/tags/*-stable'

    git -C "$TAGS_REPO" for-each-ref --sort=-creatordate --count=1 \
        --format='%(refname:strip=2)' 'refs/tags/*-stable'
}

main "$@"
