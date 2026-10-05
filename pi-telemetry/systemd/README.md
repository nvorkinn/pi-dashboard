# Deploying pi-telemetry with systemd

Runs pi-telemetry as a one-shot job once a minute via a systemd timer
(the binary publishes a single telemetry snapshot to MQTT and exits).

Each snapshot has the Pi's total and used memory, CPU count and CPU usage, and
whether countdown is running ("HAT running"). That last one comes from
`systemctl is-active countdown` rather than the process list, since no
process argument is reliably just "countdown".

## Install

Usually the repo-root [`install.sh`](../../README.md#install) does this for
you. To do it on its own, copy a pi-telemetry binary (from a release, or built
yourself) to the Pi, then run:

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

## Multiple hosts

Each host publishes to `pi-telemetry/<DEVICE_NAME>/state` and announces itself
to Home Assistant via a retained MQTT discovery message on
`homeassistant/device/<DEVICE_NAME>/config`. HA groups all of a host's sensors
under one device named after its `DEVICE_NAME`, so `DEVICE_NAME` must be unique
per host (two hosts sharing one would also fight over the same MQTT client
id). If it's unset, an older env file's `DEVICE_ID` is used, and failing that the
hostname. Sensors go `unavailable` in HA if a
host stops reporting for 3 minutes.

`countdown`'s own MQTT health reporting (`mqtt_publisher.py`) resolves
`DEVICE_NAME` the same way and reports under the same HA device, so both apps'
entities land on one device per host — see the repo root's `README.md` for
how `install.sh` sets `DEVICE_NAME` once for both.
