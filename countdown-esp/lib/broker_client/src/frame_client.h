#pragma once

// Fetching finished frames from the broker: the port of countdown_client.client.Client.

#include "display_registrar.h"
#include "ports.h"

namespace countdown {

class FrameClient {
 public:
  FrameClient(DisplayRegistrar& registrar, Http& http, Display& display, Sleeper& sleeper, Log& log);

  // One poll of /api/frame, registering first if it isn't registered (yet, or any more), then
  // waiting as long as the broker asks. Arduino's loop() calls this over and over.
  void tick();

 private:
  DisplayRegistrar& registrar_;
  Http& http_;
  Display& display_;
  Sleeper& sleeper_;
  Log& log_;
  bool registered_ = false;
};

}  // namespace countdown
