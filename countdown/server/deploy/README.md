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

1. In `docker-compose.yml`, copy the `example-screen` service, its volume and its secret, renaming
   all three and setting `DEVICE_NAME` (it labels the device on the broker).
2. Make the screen's key, which encrypts its identity in the volume (see
   [The credentials key](#the-credentials-key)).
3. `docker compose up -d <name>`.
4. Set up the screen (`countdown-client` or the ESP32). The renderer and the screen each wait in
   the broker's pool until the other arrives, then become one device; `flask devices pending` on
   the broker shows who's waiting. The renderer then draws the pairing code for the screen.

Each renderer's identity, `.auth_broker_device`, lives in its volume (`/data`). Keep the volume
and the renderer stays the same device across restarts and upgrades; remove it and the renderer
registers as a new one.

## The credentials key

`.auth_broker_device` is encrypted in the volume with a key per screen, so a copy of the volume (a backup, an
export) isn't a copy of the device's identity. Make one next to `docker-compose.yml`:

```sh
sudo install -d -m 700 keys
sudo sh -c 'head -c 32 /dev/urandom | base64 | tr "+/" "-_" > keys/<name>'
sudo chmod 444 keys/<name>   # the container's user isn't root; the 700 directory is what keeps others out
```

Keep it somewhere backed up as well: without it the encrypted file can't be read, and the renderer refuses to
start rather than quietly becoming a new device. To start over, remove the volume's `.auth_broker_device`.
A renderer that already has a plain file keeps its identity: it's encrypted the first time the key is there.

The key protects the volume on its own, not the host: anyone who can read both `keys/` and the volume has both.

There's no Fluent Bit in the container. Its health metrics go to the host's own Fluent Bit at `127.0.0.1:4318` (the
compose file uses host networking so the container can reach it), which also ships the host's logs; the renderer
needs no token. Without a Fluent Bit listening there it logs a warning each minute.

## Day to day

```sh
docker compose logs -f <name>            # what a renderer is doing
docker compose pull && docker compose up -d   # upgrade to the latest promoted release
```

To hold back, set `COUNTDOWN_SERVER_VERSION=<tag>` in a `.env` next to `docker-compose.yml`.
