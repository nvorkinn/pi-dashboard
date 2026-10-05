# countdown-esp

ESP32 firmware for the countdown, built with [PlatformIO](https://platformio.org/) on the Arduino framework.

## Setup

PlatformIO is installed from pip:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install platformio
```

Open `countdown/countdown-esp` as the folder in VS Code and accept the recommended PlatformIO IDE extension (listed in `.vscode/extensions.json`).

## Common commands

Run these from this directory (`countdown/countdown-esp`):

```sh
pio run                       # build every environment in platformio.ini
pio run -t upload             # build and flash the board on the default serial port
pio device monitor            # open the serial monitor (115200 baud)
pio test -e esp32dev          # run the tests in test/ on a connected board
```

The firmware image ends up at `.pio/build/esp32dev/firmware.bin`.

## Layout

- `platformio.ini`: build environments (`esp32dev` by default)
- `src/`: firmware sources, starting at `main.cpp`
- `include/`: project headers
- `lib/`: project-private libraries
- `test/`: PlatformIO unit tests

## CI

`.github/workflows/firmware.yml` builds every environment on pushes and pull requests that touch this directory and uploads the `.bin` files as a `firmware` artifact. Release tags (`v*`) also build it through `release.yml`, which attaches the binaries to the GitHub release.
