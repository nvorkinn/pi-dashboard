#pragma once

#include <cstdint>
#include <vector>

#include "epd7in5_v2.h"
#include "ports.h"

namespace countdown {

// Draws the broker's frames on the 7.5" V2 panel, as countdown_client's Client._display_frame does:
// wake the panel, draw, and put it back into deep sleep.
class EpdDisplay : public Display {
 public:
  EpdDisplay(Epd7in5V2& panel, Log& log) : panel_(panel), log_(log) {}

  bool show(const std::vector<uint8_t>& frame) override;

 private:
  Epd7in5V2& panel_;
  Log& log_;
};

}  // namespace countdown
