# countdown-esp

ESP32 firmware for the countdown, built with [PlatformIO](https://platformio.org/) on the Arduino framework.

It is a countdown display: the ESP32 port of `countdown-client` (`../countdown/client`). It registers
with [auth-broker](https://github.com/nvorkinn/auth-broker) as a `display`, then polls `/api/frame` for
frames that a renderer has drawn. Drawing them on the e-paper panel comes later; for now it logs each
frame it gets and throws it away.

## Setup

PlatformIO is installed from pip:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install platformio
```

Open `countdown-esp` as the folder in VS Code and accept the recommended PlatformIO IDE extension (listed in `.vscode/extensions.json`).

## Common commands

Run these from this directory (`countdown-esp`):

```sh
pio run -e esp-wrover-kit     # build the firmware
pio run -t upload             # build and flash the board on the default serial port
pio device monitor            # open the serial monitor (115200 baud)
pio test -e native            # run the unit tests in test/ on this machine
pio run -t erase              # wipe the flash, NVS included (forgets Wi-Fi and the device secret)
```

The broker URL is a build flag, `BROKER_URL` in `platformio.ini`. To point a build somewhere else:

```sh
PLATFORMIO_BUILD_FLAGS='-DBROKER_URL=\"http://192.168.1.10:8000\"' pio run -t upload
```

The firmware image ends up at `.pio/build/esp-wrover-kit/firmware.bin`.

### Coverage

The native tests are built with `--coverage`. With [gcovr](https://gcovr.com/) (macOS needs the `--gcov-executable` part):

```sh
pio test -e native
gcovr --root . --filter lib/ --gcov-executable "xcrun llvm-cov gcov" .pio/build/native
```

## First boot

1. With no Wi-Fi saved in NVS (`WIFI_SSID`, `WIFI_PASSWORD`), or if the saved network can't be joined
   within 30 seconds, the board opens a set-up portal: an open Wi-Fi network named `countdown-XXXX`.
   Join it and pick the network on the page that opens (or browse to `192.168.4.1`). The board saves
   what you enter to NVS. If nobody sets it up within 5 minutes, it restarts and tries again.
2. It makes a device secret (like Python's `secrets.token_urlsafe(24)`), saves it to NVS as
   `device_secret`, and registers with the broker. It registers again on every boot, with the same secret.
3. It polls `/api/frame`, waiting as long as the broker's `Retry-After` says (60 seconds if it doesn't).
   The broker answers 202 until it matches the display with a renderer.

## Layout

- `platformio.ini`: build environments: `esp-wrover-kit` (the default) and `native` (the unit tests)
- `lib/broker_client/`: registering and polling for frames, in plain C++ with no Arduino, so it can be
  tested on the host. What it needs from the board (HTTP, NVS, randomness, sleeping, logging) are the
  interfaces in `ports.h`
- `src/`: the ESP32 side: `main.cpp`, the ports' implementations (`esp_ports.cpp`), the Wi-Fi set-up
  portal (`wifi_setup.cpp`) and the broker's pinned root certificates (`root_certs.h`)
- `test/test_broker_client/`: Unity tests for `lib/broker_client`, with fakes of the ports
- `include/`: project headers

## CI

`.github/workflows/firmware.yml` runs the native tests (uploading coverage to Codecov under the `countdown-esp` flag) and builds the `esp-wrover-kit` firmware on pushes and pull requests that touch this directory, uploading the `.bin` as a `firmware` artifact. Release tags (`v*`) also build it through `release.yml`, which attaches the binaries to the GitHub release.
