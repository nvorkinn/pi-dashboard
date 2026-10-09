# countdown-esp

ESP32 firmware for the countdown, built with [PlatformIO](https://platformio.org/) on the Arduino framework.

It is a countdown display: the ESP32 port of `countdown-client` (`../countdown/client`). It registers
with [auth-broker](https://github.com/nvorkinn/auth-broker) as a `display`, then polls `/api/frame` for
frames that a renderer has drawn and puts them on a Waveshare 7.5" e-paper panel, the same one the Pi uses.
Each poll also carries the board's logs and metrics to the broker.

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
   what you enter to NVS and closes the portal once it's connected. If nobody sets it up within
   5 minutes, it restarts and tries the saved network again.
   On an iPhone, if the set-up page doesn't appear within a few seconds, tap ⓘ next to the network,
   turn off **Limit IP Address Tracking**, and rejoin. Opening Safari at `http://192.168.4.1` works too.
2. It makes a device secret (like Python's `secrets.token_urlsafe(24)`), saves it to NVS as
   `device_secret`, and registers with the broker. It registers again on every boot, with the same secret.
3. It polls `/api/frame` with a `POST`, waiting as long as the broker's `Retry-After` says (60 seconds
   if it doesn't). The broker answers 202 until it matches the display with a renderer. See
   [What each poll sends](#what-each-poll-sends).
4. Each new frame (a `200`) is drawn on the panel: wake it, send the frame, refresh (about 4 seconds),
   and put it back into deep sleep, as `countdown-client` does on the Pi.

## What each poll sends

```json
{
  "role": "display",
  "metrics": {"uptime_s": 3600, "free_heap": 182344, "min_free_heap": 150212, "free_psram": 4100000,
              "wifi_rssi": -61, "reset_reason": 1, "logs_dropped": 0},
  "logs": [{"uptime_ms": 3599012, "level": "INFO", "message": "Got a frame (48000 bytes)"}]
}
```

- **`logs`:** every line logged since the broker last answered, oldest first, from Wi-Fi set-up on.
  They're stamped with milliseconds since boot, since the board has no wall clock.
  An answer of 200, 202, 304 or 404 clears them. When there's no answer, a 401, or anything
  else, they're kept for the next poll.
- **Limits:** to protect the heap during a long outage, the buffer holds at most 50 lines and 8 KB of messages (lines
  are cut at 512 bytes). Past that the oldest lines go, and `logs_dropped` counts them since boot.
  Serial still gets every line in full.
- **`reset_reason`:** ESP-IDF's `esp_reset_reason_t`: 1 power-on, 3 software restart, 4 panic,
  5–7 watchdogs, 8 deep sleep, 9 brownout.

## Connecting the e-paper panel

The panel is the Waveshare 7.5" V2 (800×480, black and white), driven through Waveshare's
**e-Paper HAT**, the small board the panel's flat ribbon cable plugs into. On the Pi the HAT sits on the
pin header. On the ESP32 it's wired up through the 9-pin connector on its side, with the cable Waveshare
includes, or any female-to-female jumper wires.

Go by the labels printed on the HAT and on the ESP32 board's edge, not by wire colour:

| HAT  | ESP32   | What it does |
|------|---------|--------------|
| VCC  | 3V3     | Power (3.3 V, not 5 V) |
| GND  | GND     | Ground |
| DIN  | GPIO 14 | Data to the panel (SPI MOSI) |
| CLK  | GPIO 13 | SPI clock |
| CS   | GPIO 15 | Chip select |
| DC   | GPIO 33 | Command or data |
| RST  | GPIO 26 | Reset |
| BUSY | GPIO 25 | The panel says it's still working |
| PWR  | GPIO 32 | Turns the HAT on and off. Leave it unconnected on a HAT without a PWR pin |

- **Where the pinout comes from:** it follows Waveshare's own e-Paper ESP32 Driver Board, except DC,
  which moves from 27 to 33 because this board's RGB LED is on 27.
- **Pins it avoids:** GPIO 16 and 17 (the WROVER module's PSRAM) and the boot-sensitive pins 0, 2 and 12.
- **Changing pins:** each pin is an `EPD_PIN_*` build flag in `platformio.ini`. For a HAT without PWR,
  set `-DEPD_PIN_PWR=-1`.
- **The HAT's switches:** if the HAT has an "Interface Config" switch, set it to 0 (4-wire SPI).
  Leave "Display Config" as it was on the Pi.

If the panel isn't connected or powered, each frame logs `The e-paper panel didn't answer` after
10 seconds, and the board carries on polling.

The board's ESP32-WROVER-IE module has no antenna of its own. Plug a 2.4 GHz antenna into its u.FL
connector, or Wi-Fi only reaches a few metres.

## Layout

- `platformio.ini`: build environments: `esp-wrover-kit` (the default) and `native` (the unit tests)
- `lib/broker_client/`: registering and polling for frames, in plain C++ with no Arduino, so it can be
  tested on the host. What it needs from the board (HTTP, NVS, randomness, sleeping, logging, a clock,
  metrics, a display) are the interfaces in `ports.h`. `log_buffer.h` keeps log lines until the broker has them
- `lib/epd/`: the 7.5" V2 panel driver, ported command for command from
  `../countdown/epd/src/countdown_epd/epd7in5_V2.py`. It drives the HAT's wires through the `EpdBus`
  interface in `epd_bus.h`
- `src/`: the ESP32 side: `main.cpp`, the ports' implementations (`esp_ports.cpp`), the Wi-Fi set-up
  portal (`wifi_setup.cpp`), the HAT's wires over SPI (`esp_epd_bus.cpp`) and the broker's pinned root
  certificates (`root_certs.h`)
- `test/test_broker_client/`: Unity tests for `lib/broker_client`, with fakes of the ports
- `test/test_epd/`: Unity tests for `lib/epd`, against a fake HAT that records every command and wire change
- `include/`: project headers

## CI

`.github/workflows/firmware.yml` runs the native tests (uploading coverage to Codecov under the `countdown-esp` flag) and builds the `esp-wrover-kit` firmware on pushes and pull requests that touch this directory, uploading the `.bin` as a `firmware` artifact. Release tags (`v*`) also build it through `release.yml`, which attaches the binaries to the GitHub release.
