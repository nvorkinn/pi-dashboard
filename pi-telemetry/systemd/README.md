# Deploying pi-telemetry with systemd

Runs pi-telemetry as a one-shot job once a minute via a systemd timer
(the binary publishes a single telemetry snapshot to MQTT and exits).

## Install

Build a release binary and copy it to the Pi (see the main
[`README.md`](../README.md)), then run:

```sh
sudo ./install.sh /path/to/pi-telemetry
```

This installs the binary to `/opt/pi-telemetry`, creates
`/etc/pi-telemetry/env` from `env.example` (if it doesn't already exist —
edit it afterwards with the real broker host/port/credentials), installs
the systemd units, and enables the timer. The binary, env file, and service
are owned by/run as whoever invoked `sudo` (or `root`, if run without
`sudo`) -- `pi-telemetry.service`'s `User=@USER@` placeholder gets
substituted with that user by the script, it's not a real username in the
committed file.

### Manual steps

If you'd rather do it by hand, or need to see exactly what the script
does (using `vorkin` as an example target user):

```sh
sudo mkdir -p /opt/pi-telemetry
sudo cp pi-telemetry /opt/pi-telemetry/pi-telemetry
sudo chown vorkin:vorkin /opt/pi-telemetry/pi-telemetry

sudo mkdir -p /etc/pi-telemetry
sudo cp systemd/env.example /etc/pi-telemetry/env
sudo chmod 600 /etc/pi-telemetry/env
sudo chown vorkin:vorkin /etc/pi-telemetry/env
# edit /etc/pi-telemetry/env with the real broker host/port/credentials

sed "s/@USER@/vorkin/" systemd/pi-telemetry.service | sudo tee /etc/systemd/system/pi-telemetry.service > /dev/null
sudo cp systemd/pi-telemetry.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pi-telemetry.timer
```

## Verify

```sh
systemctl status pi-telemetry.timer
systemctl list-timers pi-telemetry.timer
journalctl -u pi-telemetry.service -f
```

## Updating

After copying a new binary to `/opt/pi-telemetry/pi-telemetry`, no service
restart is needed — the next timer tick picks it up automatically, since
each run starts a fresh process.
