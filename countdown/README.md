# countdown

The long-running Python app that drives the 7.5" Waveshare e-paper display:
TfL arrivals, weather, a notice board, Glowmarkt energy use and Spotify, all
configured remotely through [auth-broker](https://github.com/nvorkinn/auth-broker).

## How it works

**Boot** (`app.py`). The app reads `BROKER_URL` and registers with the broker
before it does anything else (`countdown_credentials/registration.py`), standalone
and split alike. On first run that saves its credentials to `.auth_broker_device`
in the working directory; later runs just load them. A split renderer also waits
there until a screen has been matched with it. Then it sets up the display and
waits for a valid config. The app can't run without that config, so there's no
empty fallback: if the broker can't be reached or sends back something invalid,
it keeps retrying, backing off from 30 seconds to 5 minutes. Nothing is painted
until it has a config. Once it's running, a failed config refresh just keeps the
config it already has.

**The loop** (`display_loop.py`). Every `interval` seconds (set in the config),
the device is in one of three stages:

- *pairing*: the config carries a pairing code, so the device shows it full
  screen. It's only repainted when the code changes.
- *setup*: paired, but `setup_missing` isn't empty (it needs a weather location
  and at least one bus or tube stop). A "You're paired!" checklist is shown and
  no API is polled.
- *running*: the dashboard.

After each cycle the loop publishes health over OTLP (see
[Deploying](#deploying-to-a-raspberry-pi)) and re-reads the config from the
broker. The broker has no change notification, so this poll is how changes to
stops, credentials and so on reach the device, and how the pairing code stays
current.

**API clients** (`*_client.py`, `api_registry.py`). Each API has an
`AbstractClient` subclass: TfL arrivals, Open-Meteo weather, Glowmarkt energy,
Spotify (proxied by the broker, so the device never holds a Spotify token) and
the notice board. `ApiRegistry` builds a client for every API the config enables.
When the config changes, it only rebuilds the clients whose `needs_refresh()`
says the change affects them. Each client has its own `poll_interval`. The
clients that are due are polled concurrently, with their blocking `requests`
calls running in worker threads, so a cycle takes as long as the slowest API.
A client that isn't due, or whose poll failed, keeps its last panel. An API
with no panel at all gets a `MessagePanel` ("Not configured", "Could not
connect"). A client that failed to initialise tries again on its next poll, and
one broken API never takes the others down.

**Notice board** (`notice_board_client.py`, `notices/`). This covers TfL line
status and station disruptions for the configured stops, Met Office warnings,
Environment Agency flood alerts and TfL road incidents near the owner's postcode
(looked up with postcodes.io), and bank holidays and clock changes. Each source
has its own refresh interval. A failing source keeps its last notices for a
while (at least an hour) before they're dropped. Notices are ranked by severity, and planned works only fill rows left
over.

**Layout** (`display_composers/`). Which APIs are available decides the layout:
Glowmarkt is on only when the config has both its credentials, and Spotify when
it's enabled. There's one composer for each combination of the two. Every layout
puts the arrivals top-left with the weather beside them. The layout also sets
how many stops are on screen at once (four with neither Spotify nor Glowmarkt,
otherwise two), and the TfL client pages through the rest.

**Painting** (`core/display.py`, `core/targets.py`). `DisplayController`
only paints when the picture changes. If only the arrivals changed, it does a
quick partial refresh of their box. Otherwise, or once 10 minutes have passed
since the last full refresh (partial refreshes leave ghosting), it does a full
refresh. If every API only has a message to show, a "Nothing to show yet" screen
replaces the dashboard. Frames go to a display target (see below). If no panel
answers, the app runs without a display and checks again every 5 minutes, and a
whole-screen picture it couldn't paint (pairing code, checklist) is
retried once the panel appears.

## Packages

This directory is a uv workspace with three packages:

- `core/` (`countdown-core`): the app itself: clients, panels, layouts and the
  display loop, with no e-paper hardware dependencies. A library only: it has
  no script of its own, and the other two depend on it.
- `standalone/` (`countdown-standalone`): what runs on the Pi. It adds the
  vendored Waveshare driver (`countdown_standalone/lib`) and its GPIO/SPI
  dependencies, and paints on the panel.
- `server/` (`countdown-server`): the app without the e-paper driver (work in
  progress).

`uv sync` installs all three, editable, for development and the tests.

## Running locally

```bash
BROKER_URL=https://auth.nikolaivorkinn.com uv run countdown-standalone
```

`DISPLAY_TARGET` picks where frames go:

- `epd`: the panel on this Pi (`countdown-standalone` only).
- `preview`: the local image viewer.
- `remote`: a Pi over ssh. `PI_HOST` (e.g. `nikolai@countdown.local`) is
  required, and `PI_DIR` defaults to `countdown-dev`. Each frame is rsynced
  to the Pi with `dev/pi_display.py`, which paints it using the driver from the
  installed release. Stop the service on the Pi first
  (`sudo systemctl stop countdown`), or it paints over your frames. Start it
  again when you're done. `uv run dev/clear_pi.py`, with the same variables,
  blanks the panel.
- `auto` (the default): in `countdown-standalone`, the panel if its driver
  loads, otherwise the image viewer. Without the driver (`countdown-core` on
  its own), the image viewer.

`LOG_LEVEL` (e.g. `DEBUG`) overrides the default `INFO`.

## Visual Regression Testing

The rendered e-paper screen is tested by comparing it against golden PNGs
checked into `tests/images/`, rather than only asserting on the data that
feeds it. `tests/test_display_snapshots.py` builds each scenario (arrivals,
energy, weather, Spotify now-playing, empty states, etc.) directly from
representative data and renders it through the real `DisplayController`.

### Running it

```bash
pytest tests/test_display_snapshots.py
```

Compares each scenario's render against its golden image in `tests/images/`.
On a mismatch, the test fails with the actual render and a red-highlighted
diff written to `tests/images/_failures/<name>.actual.png` /
`<name>.diff.png` so you can see exactly what changed.

### Updating goldens after an intentional change

```bash
pytest tests/test_display_snapshots.py --update-snapshots
```

This only rewrites the golden images for scenarios whose render actually
changed -- `git status` afterwards shows exactly which ones. Review the new
PNGs, then commit them alongside your code change.

### Reviewing in a PR

Since the goldens are just PNGs committed to the repo, GitHub's own "Files
changed" view renders a visual diff (2-up / swipe / onion-skin) for any
changed image automatically -- no extra tooling needed. The loop is:
change code -> run tests (see what broke) -> `--update-snapshots` if the new
output is correct -> commit the changed PNGs -> open a PR -> review the
image diffs on GitHub -> merge.

### Adding a new scenario

Add a function to `tests/test_display_snapshots.py` that builds the panels
it needs and calls `snapshot.assert_matches("some_name", image)`. Run with
`--update-snapshots` once to create its golden image, review it, and commit
it.

## Deploying to a Raspberry Pi

Each tagged release publishes the `countdown-standalone` and `countdown-core`
wheels and a `countdown.service` unit to
GitHub Releases (see `.github/workflows/release.yml` at the repo root; the tag is the repo-wide one). `packaging/install.sh`
downloads a release, installs it with `uv tool install` (as the
`countdown-standalone` tool), and sets it up as a
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

From there `install.sh` uses the [`gh` CLI](https://cli.github.com), installing
it if it's missing (see the [root README](../README.md) for why).

If you're provisioning a Pi with Fluent Bit too (which ships its logs and metrics), use the repo-root
[`install.sh`](../README.md#install) instead -- it wraps this installer and
installs everything else you need in one command.

This installs `uv` for the invoking user if it isn't already present, and
runs the service as that user. Re-running the installer updates the app and
restarts the service.

There's no local config file: on first boot the app registers itself with
[auth-broker](https://github.com/nvorkinn/auth-broker) and shows a pairing code
on the display. Go to https://nikolaivorkinn.com,
enter the code, and manage everything from there: TfL stops, refresh
interval, weather location, Glowmarkt energy account, and connecting Spotify
(the broker handles the OAuth handshake and proxies now-playing calls, so
this device never holds a Spotify token itself). The code is only shown
once per device; credentials persist in `/opt/countdown/.auth_broker_device`
across restarts.

Once paired, the device shows a checklist of anything still missing (see
[How it works](#how-it-works)).

The only local setting left is which broker to talk to
(`BROKER_URL`, set via the systemd unit's `Environment=` line -- see
`packaging/systemd/countdown.service`), since that's what the device needs
in order to find the broker in the first place. Everything else -- including
Glowmarkt credentials, which are the frame owner's own energy account and
never shared with other devices -- comes from there, so there's no local
secret file on the device at all.

Countdown reports its health as OTLP/HTTP metrics (protobuf, via the OpenTelemetry Python SDK) to the local Fluent Bit's
OpenTelemetry input at `http://127.0.0.1:4318/v1/metrics`. They're tagged with
`host.name`, the `DEVICE_NAME` that `install.sh` wrote to `/etc/countdown/env`
(see the repo root's README). Gauges:

- `countdown.api.status`: 1 per API, with `api` and `status` attributes
- `countdown.problem`: 1 while any API is in `error` or `fatal`
- `countdown.stage`: 1, with a `stage` attribute
- `countdown.display.connected`: whether the panel is connected
- `countdown.broker.last_sync`: Unix time of the last broker sync (absent until the first)

It reports from the moment the app starts, from its own background task, so a
device still registering with the broker shows up (as `waiting_for_broker`). Metrics
are sent once a minute, and straight away when the stage changes. A failed send is
logged and retried at the next interval. The env file is only read when the service
starts, so restart countdown (`sudo systemctl restart countdown`) after editing it.

Once the broker has accepted the registration, a standalone countdown (not `countdown-server`) writes the device secret and `DEVICE_NAME` to the file
`FLUENT_BIT_ENV_FILE` points at (`/etc/fluent-bit/env`, set in the unit), which is what starts Fluent Bit shipping
the Pi's logs and metrics (see the repo root's README). Without that variable set, it does nothing.

Once installed:

```bash
systemctl status countdown   # check it's running
journalctl -u countdown -f   # tail its logs
```

The invoking user needs access to the e-paper hardware (typically the `gpio`
and `spi` groups on Raspberry Pi OS) for the display to actually render.
