# Visual Regression Testing

The rendered e-paper screen is tested by comparing it against golden PNGs
checked into `tests/images/`, rather than only asserting on the data that
feeds it. `tests/test_display_snapshots.py` builds each scenario (arrivals,
energy, weather, Spotify now-playing, empty states, etc.) directly from
representative data and renders it through the real `DisplayController`.

## Running it

```bash
pytest tests/test_display_snapshots.py
```

Compares each scenario's render against its golden image in `tests/images/`.
On a mismatch, the test fails with the actual render and a red-highlighted
diff written to `tests/images/_failures/<name>.actual.png` /
`<name>.diff.png` so you can see exactly what changed.

## Updating goldens after an intentional change

```bash
pytest tests/test_display_snapshots.py --update-snapshots
```

This only rewrites the golden images for scenarios whose render actually
changed -- `git status` afterwards shows exactly which ones. Review the new
PNGs, then commit them alongside your code change.

## Reviewing in a PR

Since the goldens are just PNGs committed to the repo, GitHub's own "Files
changed" view renders a visual diff (2-up / swipe / onion-skin) for any
changed image automatically -- no extra tooling needed. The loop is:
change code -> run tests (see what broke) -> `--update-snapshots` if the new
output is correct -> commit the changed PNGs -> open a PR -> review the
image diffs on GitHub -> merge.

## Adding a new scenario

Add a function to `tests/test_display_snapshots.py` that builds the panels
it needs and calls `snapshot.assert_matches("some_name", image)`. Run with
`--update-snapshots` once to create its golden image, review it, and commit
it.

# Deploying to a Raspberry Pi

Each tagged release publishes a wheel and a `countdown.service` unit to
GitHub Releases (see `.github/workflows/release.yml` at the repo root; the release is shared with pi-telemetry, so the tag is the repo-wide one). `packaging/install.sh`
downloads a release, installs it with `uv tool install`, and sets it up as a
systemd service.

This repo (`pi-dashboard`) is private, so every fetch it does (including fetching the
installer itself) needs a GitHub token with read access to it. Nothing is
ever fetched from `main` -- `install.sh` is pinned to a tagged release like
everything else it downloads, so resolve one (or use `latest`, via the
releases API) before the first `curl`:

```bash
export GITHUB_TOKEN=github_pat_...

# Pin an exact version, or leave as "latest":
VERSION=latest
if [ "$VERSION" = latest ]; then
    TAG="$(curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
        https://api.github.com/repos/nvorkinn/pi-dashboard/releases/latest \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
else
    TAG="$VERSION"
fi

curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
    "https://raw.githubusercontent.com/nvorkinn/pi-dashboard/$TAG/countdown/packaging/install.sh" \
    | GITHUB_TOKEN="$GITHUB_TOKEN" sudo -E bash -s -- "$TAG"
```

`install.sh` itself uses the [`gh` CLI](https://cli.github.com) to resolve releases and download assets from that point on (installing it automatically if it's missing) -- `gh` handles private-repo auth correctly on its own, where a hand-rolled `curl` approach needs a separate asset-API dance.

If you're provisioning a Pi with pi-telemetry too, use the repo-root
[`install.sh`](../README.md#install) instead -- it wraps this installer and
installs everything else you need in one command.

This installs `uv` for the invoking user if it isn't already present, and
runs the service as that user. Re-running the installer updates the app and
restarts the service.

There's no local config file or website any more -- on first boot the app
registers itself with [auth-broker](https://github.com/nvorkinn/auth-broker)
and shows a pairing code on the display. Go to https://nikolaivorkinn.com,
enter the code, and manage everything from there: TfL stops, refresh
interval, weather location, Glowmarkt energy account, and connecting Spotify
(the broker handles the OAuth handshake and proxies now-playing calls, so
this device never holds a Spotify token itself). The code is only shown
once per device; credentials persist in `/opt/countdown/.auth_broker_device`
across restarts.

The only local setting left is which broker to talk to
(`BROKER_URL`, set via the systemd unit's `Environment=` line -- see
`packaging/systemd/countdown.service`), since that's what the device needs
in order to find the broker in the first place. Everything else -- including
Glowmarkt credentials, which are the frame owner's own energy account and
never shared with other devices -- comes from there, so there's no local
secret file on the device at all.

Reporting API health to Home Assistant is optional and configured the same way as
[pi-telemetry](../pi-telemetry/), which it sits alongside: the
service loads `/etc/pi-telemetry/env` (if it exists) for `MQTT_BROKER_HOST`,
`MQTT_BROKER_PORT`, `MQTT_BROKER_USERNAME`, `MQTT_BROKER_PASSWORD` and `DEVICE_ID`.
With no `MQTT_BROKER_HOST` it doesn't publish at all. Countdown adds a status sensor
per API and an "API problem" sensor to the same Home Assistant device as
pi-telemetry's (same `DEVICE_ID`), publishing to `pi-telemetry/<DEVICE_ID>/countdown/state`.
The env file is only read when the service starts, so restart countdown
(`sudo systemctl restart countdown`) after installing pi-telemetry or editing it.

Once installed:

```bash
systemctl status countdown   # check it's running
journalctl -u countdown -f   # tail its logs
```

The invoking user needs access to the e-paper hardware (typically the `gpio`
and `spi` groups on Raspberry Pi OS) for the display to actually render.
