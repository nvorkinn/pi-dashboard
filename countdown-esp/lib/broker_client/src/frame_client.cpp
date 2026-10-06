#include "frame_client.h"

#include <string>

#include "retry.h"

namespace countdown {

FrameClient::FrameClient(DisplayRegistrar& registrar, Http& http, Display& display, Sleeper& sleeper,
                         Log& log)
    : registrar_(registrar), http_(http), display_(display), sleeper_(sleeper), log_(log) {}

void FrameClient::tick() {
  if (!registered_) {
    registrar_.registerDevice();
    registered_ = true;
  }
  const std::string url = registrar_.brokerUrl() + "/api/frame";
  const HttpResponse response = http_.request("GET", url, R"({"role":"display"})", registrar_.secret());
  if (!response.sent) {
    log_.warning("Couldn't fetch the frame: " + response.error);
    sleeper_.sleepSeconds(kDefaultRetryS);
    return;
  }
  switch (response.status) {
    case 200:
      log_.info("Got a frame (" + std::to_string(response.body.size()) + " bytes)");
      // Where the Pi's client would crash (and systemd restart it), this logs and carries on
      // polling: the next frame the broker sends is drawn as usual.
      if (!display_.show(response.body)) {
        log_.error("Couldn't draw the frame");
      }
      break;
    case 202:  // Not matched with a renderer yet
    case 304:  // Nothing has changed since last poll
    case 404:  // Matched, but nothing rendered yet
      break;
    case 401:  // The broker doesn't know the secret (dropped from the pool, or unlinked)
      registered_ = false;
      return;
    default:
      log_.warning("Unexpected " + std::to_string(response.status) + " from " + url);
      break;
  }
  sleeper_.sleepSeconds(retryAfterSeconds(response.retryAfter));
}

}  // namespace countdown
