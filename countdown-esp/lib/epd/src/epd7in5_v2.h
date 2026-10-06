#pragma once

// The Waveshare 7.5" V2 panel (800×480, black and white): the port of
// countdown/epd/src/countdown_epd/epd7in5_V2.py, the driver the Pi uses, command for command.

#include <cstddef>
#include <cstdint>
#include <initializer_list>

#include "epd_bus.h"

namespace countdown {

class Epd7in5V2 {
 public:
  static constexpr int kWidth = 800;
  static constexpr int kHeight = 480;
  // One bit per pixel, a row at a time: what the broker's frames are.
  static constexpr size_t kFrameBytes = kWidth / 8 * kHeight;

  // How long a BUSY wait lasts before giving up. A full refresh takes a few seconds, so this is
  // generous (BUSY_TIMEOUT_S).
  static constexpr uint32_t kBusyTimeoutMs = 60 * 1000;
  // How long init() waits for the POWER ON handshake. A connected panel answers in well under a
  // second, so silence for this long means there's no panel, or it isn't powered (POWER_ON_TIMEOUT_S).
  static constexpr uint32_t kPowerOnTimeoutMs = 10 * 1000;

  explicit Epd7in5V2(EpdBus& bus) : bus_(bus) {}

  // Each returns false when the panel stops answering (BUSY never releases); the HAT is then
  // powered off, so the next init() starts from a clean slate.
  bool init();
  // `frame` is kFrameBytes long.
  bool display(const uint8_t* frame);
  bool sleep();

 private:
  void reset();
  void command(uint8_t command, std::initializer_list<uint8_t> data = {});
  bool waitBusy(uint32_t timeoutMs);

  EpdBus& bus_;
};

}  // namespace countdown
