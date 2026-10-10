#!/usr/bin/env bash
# Provisions a Pi with countdown and Fluent Bit (which ships the Pi's logs and metrics), from one tagged
# release: decrypts countdown's secrets, runs its installer, and schedules
# check_update.sh to keep the Pi on the latest release. See README.md.
#
# Usage:
#   curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
#       "https://raw.githubusercontent.com/nvorkinn/pi-dashboard/<tag>/install.sh" \
#       | sudo -E env GITHUB_TOKEN="$GITHUB_TOKEN" bash -s -- \
#           <tag> <device name>
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root (it installs systemd units). Re-run with sudo." >&2
    exit 1
fi

TAG="${1:?TAG is required -- pass the exact tag this script was fetched from}"
RAW_DEVICE_NAME="${2:?device name is required -- pass it as the second argument (e.g. \"sister-hat\")}"

# Same rules as countdown_credentials/device_name.py.
DEVICE_NAME="$(printf '%s' "$RAW_DEVICE_NAME" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')"
if [ -z "$(printf '%s' "$DEVICE_NAME" | tr -d '-')" ]; then
    echo "Device name \"$RAW_DEVICE_NAME\" has no usable characters (need at least one of a-z, 0-9, _)." >&2
    exit 1
fi

REPO="nvorkinn/pi-dashboard"

export COUNTDOWN_APP_DIR="${COUNTDOWN_APP_DIR:-/opt/countdown}"
COUNTDOWN_ENV_FILE="/etc/countdown/env"

STATE_DIR="/etc/pi-setup"
TOKEN_FILE="$STATE_DIR/github-token"
KEY_FILE="$STATE_DIR/age-key.txt"
DEVICE_NAME_FILE="$STATE_DIR/device-name"
# What DEVICE_NAME_FILE was called before; replaced by it below.
LEGACY_DEVICE_ID_FILE="$STATE_DIR/device-id"
INSTALL_USER_FILE="$STATE_DIR/install-user"
INSTALLED_TAG_FILE="$STATE_DIR/installed-tag"

umask 077
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

TMP_DIR="$(mktemp -d)"
chmod 755 "$TMP_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT

PREVIOUS_NAME_FILE="$DEVICE_NAME_FILE"
[ -f "$PREVIOUS_NAME_FILE" ] || PREVIOUS_NAME_FILE="$LEGACY_DEVICE_ID_FILE"
if [ -f "$PREVIOUS_NAME_FILE" ] && [ "$(cat "$PREVIOUS_NAME_FILE")" != "$DEVICE_NAME" ]; then
    echo "Warning: changing device name from \"$(cat "$PREVIOUS_NAME_FILE")\" to \"$DEVICE_NAME\"." >&2
    echo "         Its logs and metrics will show up under the new name." >&2
fi
echo "$DEVICE_NAME" > "$DEVICE_NAME_FILE"
rm -f "$LEGACY_DEVICE_ID_FILE"
echo "Device name: $DEVICE_NAME"

# The apps are installed for whoever ran sudo. check_update.sh runs this from a
# systemd timer, without sudo, so it reuses the user from the first install.
if [ -n "${SUDO_USER:-}" ]; then
    echo "$SUDO_USER" > "$INSTALL_USER_FILE"
elif [ -f "$INSTALL_USER_FILE" ]; then
    SUDO_USER="$(cat "$INSTALL_USER_FILE")"
fi
export SUDO_USER="${SUDO_USER:-root}"

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

# Installers, units and env templates come from the source archive at the tag.
echo "Fetching source at $TAG..."
mkdir -p "$TMP_DIR/src-archive" "$TMP_DIR/src"
gh release download "$TAG" --repo "$REPO" --archive tar.gz \
    --dir "$TMP_DIR/src-archive" --clobber
tar -xzf "$TMP_DIR"/src-archive/*.tar.gz -C "$TMP_DIR/src" --strip-components=1

# Decrypts secrets/<name>.age from the bundle, or returns 1 if there isn't one.
fetch_secret() {
    local name="$1" out_file="$2"
    local src="$TMP_DIR/bundle/secrets/$name.age"
    if [ -f "$src" ]; then
        age -d -i "$KEY_FILE" "$src" > "$out_file"
        return 0
    fi
    return 1
}

# Writes an env file (mode 600) from the given KEY=value lines.
write_env_file() {
    local file="$1"
    shift
    install -d -m 755 "$(dirname "$file")"
    printf '%s\n' "$@" > "$file"
    chmod 600 "$file"
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

GITHUB_TOKEN="$GITHUB_TOKEN" bash "$TMP_DIR/src/countdown/packaging/install.sh" "$TAG"

# countdown's unit reads this for DEVICE_NAME. Not a secret, and the service user isn't root.
write_env_file "$COUNTDOWN_ENV_FILE" "DEVICE_NAME=$DEVICE_NAME"
chmod 644 "$COUNTDOWN_ENV_FILE"
systemctl restart countdown

# pi-telemetry, which fluent-bit replaced.
if [ -d /opt/pi-telemetry ] || [ -d /etc/pi-telemetry ]; then
    echo "Removing pi-telemetry..."
    systemctl disable --now pi-telemetry.timer pi-telemetry.service 2>/dev/null || true
    rm -rf /opt/pi-telemetry /etc/pi-telemetry /etc/systemd/system/pi-telemetry.service /etc/systemd/system/pi-telemetry.timer
    systemctl daemon-reload
fi

echo
echo "== logs =="
install -d /etc/systemd/journald.conf.d
install -m 644 "$TMP_DIR/src/systemd/90-pi-dashboard-journal.conf" /etc/systemd/journald.conf.d/
# Moves this boot's journal from RAM onto disk too.
systemctl restart systemd-journald

echo
echo "== fluent-bit =="
if ! command -v /opt/fluent-bit/bin/fluent-bit >/dev/null 2>&1; then
    echo "Installing Fluent Bit..."
    install -d -m 755 /usr/share/keyrings
    curl -fsSL https://packages.fluentbit.io/fluentbit.key | gpg --dearmor --yes -o /usr/share/keyrings/fluentbit-keyring.gpg
    CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
    echo "deb [signed-by=/usr/share/keyrings/fluentbit-keyring.gpg] https://packages.fluentbit.io/debian/$CODENAME $CODENAME main" \
        > /etc/apt/sources.list.d/fluent-bit.list
    apt-get update
    apt-get install -y --no-install-recommends fluent-bit
fi

# countdown writes /run/countdown/fluent-bit-env (RAM) once it has registered with the broker, and Fluent Bit's own
# unit only runs once that file exists.
install -d -m 755 /etc/fluent-bit
# Where countdown wrote it before it was kept in RAM: the secret was on the SD card.
rm -f /etc/fluent-bit/env
install -m 644 "$TMP_DIR/src/fluent-bit/fluent-bit.yaml" /etc/fluent-bit/fluent-bit.yaml

install -d /etc/systemd/system/fluent-bit.service.d
sed "s|@USER@|${SUDO_USER:-root}|" "$TMP_DIR/src/systemd/fluent-bit-env.conf" \
    > /etc/systemd/system/fluent-bit.service.d/env.conf
chmod 644 /etc/systemd/system/fluent-bit.service.d/env.conf
install -m 644 "$TMP_DIR/src/systemd/fluent-bit-env.path" "$TMP_DIR/src/systemd/fluent-bit-restart.service" \
    /etc/systemd/system/
systemctl daemon-reload
systemctl enable fluent-bit fluent-bit-env.path
systemctl start fluent-bit-env.path
# Starts it if countdown has registered already, and stops the package's default instance if not.
systemctl restart fluent-bit

echo
echo "== updates =="
install -m 755 "$TMP_DIR/src/check_update.sh" /usr/local/sbin/pi-dashboard-check-update
install -m 644 "$TMP_DIR/src/systemd/pi-dashboard-update.service" \
    "$TMP_DIR/src/systemd/pi-dashboard-update.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pi-dashboard-update.timer

echo "$TAG" > "$INSTALLED_TAG_FILE"

echo
echo "Done. countdown and fluent-bit are both installed ($TAG)."
echo "  systemctl status countdown"
echo "  systemctl status fluent-bit   # runs once countdown has registered"
echo "  systemctl list-timers pi-dashboard-update.timer"
