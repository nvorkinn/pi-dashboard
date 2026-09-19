#!/usr/bin/env bash
# Installs pi-telemetry as a systemd timer-triggered service on the Pi.
# Automates the manual steps in systemd/README.md.
set -euo pipefail

usage() {
    echo "Usage: sudo ./install.sh <path-to-pi-telemetry-binary>" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || { echo "Must run as root (sudo)." >&2; exit 1; }
[ $# -eq 1 ] || usage

bin_src=$1
[ -f "$bin_src" ] || { echo "Binary not found: $bin_src" >&2; exit 1; }

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
systemd_dir="$script_dir/systemd"

service_user="${SUDO_USER:-root}"
id "$service_user" >/dev/null 2>&1 || {
    echo "User '$service_user' does not exist on this system." >&2
    exit 1
}

echo "Installing binary to /opt/pi-telemetry (owner: $service_user)"
install -d -o "$service_user" -g "$service_user" -m 755 /opt/pi-telemetry
install -o "$service_user" -g "$service_user" -m 755 "$bin_src" /opt/pi-telemetry/pi-telemetry

echo "Setting up /etc/pi-telemetry/env"
install -d -m 755 /etc/pi-telemetry
if [ -f /etc/pi-telemetry/env ]; then
    echo "  /etc/pi-telemetry/env already exists, leaving it untouched."
else
    install -o "$service_user" -g "$service_user" -m 600 "$systemd_dir/env.example" /etc/pi-telemetry/env
    echo "  Created from env.example - edit it with the real broker host/port/credentials:"
    echo "    sudo \$EDITOR /etc/pi-telemetry/env"
fi

echo "Installing systemd units"
sed "s#@USER@#$service_user#" "$systemd_dir/pi-telemetry.service" > /etc/systemd/system/pi-telemetry.service
cp "$systemd_dir/pi-telemetry.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pi-telemetry.timer

echo
echo "Done. Check status with:"
echo "  systemctl status pi-telemetry.timer"
echo "  systemctl list-timers pi-telemetry.timer"
echo "  journalctl -u pi-telemetry.service -f"
