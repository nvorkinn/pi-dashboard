#include "epd_display.h"

#include <string>

namespace countdown {

bool EpdDisplay::show(const std::vector<uint8_t>& frame) {
  if (frame.size() != Epd7in5V2::kFrameBytes) {
    log_.error("The frame is " + std::to_string(frame.size()) + " bytes; the panel takes " +
               std::to_string(Epd7in5V2::kFrameBytes));
    return false;
  }
  if (!panel_.init()) {
    log_.error("The e-paper panel didn't answer: is it connected and powered?");
    return false;
  }
  if (!panel_.display(frame.data())) {
    log_.error("The e-paper panel was still busy after drawing the frame");
    return false;
  }
  if (!panel_.sleep()) {
    log_.error("The e-paper panel didn't go to sleep");
    return false;
  }
  return true;
}

}  // namespace countdown
