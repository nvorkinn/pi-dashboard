#pragma once

// Fetching finished frames from the broker: the port of countdown_client.client.Client.

#include "display_registrar.h"
#include "log_buffer.h"
#include "ports.h"

namespace countdown {

class FrameClient {
 public:
  // `log` is where the client logs too, and what each poll sends.
  FrameClient(DisplayRegistrar& registrar, Http& http, Display& display, Sleeper& sleeper, LogBuffer& log,
              Metrics& metrics);

  // One poll of /api/frame, registering first if it isn't registered (yet, or any more), then
  // waiting as long as the broker asks. Each poll carries the board's metrics and the buffered
  // logs, which are cleared once the broker has answered. Arduino's loop() calls this over and over.
  void tick();

 private:
  DisplayRegistrar& registrar_;
  Http& http_;
  Display& display_;
  Sleeper& sleeper_;
  LogBuffer& log_;
  Metrics& metrics_;
  bool registered_ = false;
};

}  // namespace countdown
