# Running renderers with Docker

A screen that only shows frames -- a Pi running `countdown-client`, or the ESP32 -- needs a
renderer: a `countdown-server` process that draws its dashboard and hands each frame to the auth
broker, where the screen fetches it. These run on the same server as the broker, one container per
screen, from the `ghcr.io/nvorkinn/countdown-server` image.

## The image

Every release builds it from that release's own wheels and pushes it as
`ghcr.io/nvorkinn/countdown-server:<tag>`. `:latest` moves when a release is promoted to the
GitHub release marked latest -- the same release the Pis update to -- so a renderer on `:latest`
never runs an untested pre-release.

To build it locally, from `countdown/`:

```sh
uv build --wheel --all-packages
docker build -f server/Dockerfile -t countdown-server:dev .
```

## Adding a screen

1. In `docker-compose.yml`, copy the `example-screen` service and its volume, renaming both and
   setting `DEVICE_NAME` (it labels the device on the broker).
2. `docker compose up -d <name>`.
3. Set up the screen (`countdown-client` or the ESP32). The renderer and the screen each wait in
   the broker's pool until the other arrives, then become one device; `flask devices pending` on
   the broker shows who's waiting. The renderer then draws the pairing code for the screen.

Each renderer's identity, `.auth_broker_device`, lives in its volume (`/data`). Keep the volume
and the renderer stays the same device across restarts and upgrades; remove it and the renderer
registers as a new one.

There's no Fluent Bit in the container, so its health metrics (sent to `127.0.0.1:4318`) have nowhere to go: it logs a warning each minute.

## Day to day

```sh
docker compose logs -f <name>            # what a renderer is doing
docker compose pull && docker compose up -d   # upgrade to the latest promoted release
```

To hold back, set `COUNTDOWN_SERVER_VERSION=<tag>` in a `.env` next to `docker-compose.yml`.
