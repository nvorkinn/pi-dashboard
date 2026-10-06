#include "epd7in5_v2.h"

namespace countdown {

namespace {
// The inverted copy display() sends goes out in pieces this size, so it never needs a second
// frame-sized buffer.
constexpr size_t kChunkBytes = 1024;
}  // namespace

bool Epd7in5V2::init() {
  bus_.powerOn();
  reset();

  command(0x06, {0x17, 0x17, 0x28, 0x17});  // BOOSTER SOFT START
  command(0x01, {0x07, 0x07, 0x28, 0x17});  // POWER SETTING: VGH=20V, VGL=-20V, VDH=15V, VDL=-15V
  command(0x04);                            // POWER ON
  bus_.delayMs(100);
  if (!waitBusy(kPowerOnTimeoutMs)) {
    return false;
  }
  command(0x00, {0x1F});                    // PANEL SETTING: KW mode
  command(0x61, {0x03, 0x20, 0x01, 0xE0});  // RESOLUTION: 800 sources, 480 gates
  command(0x15, {0x00});                    // DUAL SPI off
  command(0x50, {0x10, 0x07});              // VCOM AND DATA INTERVAL
  command(0x60, {0x22});                    // TCON SETTING
  return true;
}

bool Epd7in5V2::display(const uint8_t* frame) {
  // The old-data RAM gets the frame inverted and the new-data RAM the frame itself, as the
  // Python driver does.
  bus_.command(0x10);
  uint8_t chunk[kChunkBytes];
  for (size_t offset = 0; offset < kFrameBytes; offset += kChunkBytes) {
    const size_t length = kFrameBytes - offset < kChunkBytes ? kFrameBytes - offset : kChunkBytes;
    for (size_t i = 0; i < length; ++i) {
      chunk[i] = static_cast<uint8_t>(~frame[offset + i]);
    }
    bus_.data(chunk, length);
  }
  bus_.command(0x13);
  bus_.data(frame, kFrameBytes);

  command(0x12);  // DISPLAY REFRESH
  bus_.delayMs(100);
  return waitBusy(kBusyTimeoutMs);
}

bool Epd7in5V2::sleep() {
  command(0x50, {0xF7});
  command(0x02);  // POWER OFF
  if (!waitBusy(kBusyTimeoutMs)) {
    return false;
  }
  command(0x07, {0xA5});  // DEEP SLEEP
  bus_.delayMs(2000);
  bus_.powerOff();
  return true;
}

void Epd7in5V2::reset() {
  bus_.setReset(true);
  bus_.delayMs(20);
  bus_.setReset(false);
  bus_.delayMs(2);
  bus_.setReset(true);
  bus_.delayMs(20);
}

void Epd7in5V2::command(uint8_t command, std::initializer_list<uint8_t> data) {
  bus_.command(command);
  for (const uint8_t byte : data) {
    bus_.data(byte);
  }
}

// The Python driver's ReadBusy: asks for the status (0x71) and checks BUSY every 20 ms, giving up
// after `timeoutMs` and powering the HAT off.
bool Epd7in5V2::waitBusy(uint32_t timeoutMs) {
  const uint32_t start = bus_.millis();
  bus_.command(0x71);
  while (bus_.busy()) {
    if (bus_.millis() - start > timeoutMs) {
      bus_.powerOff();
      return false;
    }
    bus_.delayMs(20);
    bus_.command(0x71);
  }
  bus_.delayMs(20);
  return true;
}

}  // namespace countdown
