#include "frame_client.h"

#include <deque>
#include <string>
#include <vector>

#include "json.h"
#include "line_protocol.h"
#include "retry.h"

namespace countdown {

namespace {

const char* levelName(LogLevel level) {
  switch (level) {
    case LogLevel::Error:
      return "ERROR";
    case LogLevel::Warning:
      return "WARNING";
    default:
      return "INFO";
  }
}

// The metrics' InfluxDB measurement and tags. The broker swaps in the device_id it authenticated
// the poll as, so the board never has to claim one.
constexpr char kMetricsSeriesKey[] = "esp32,device_id={device_id}";

// {"role":"display","metrics":"<line protocol>","logs":[{"uptime_ms":...,"level":...,"message":...},...]}
std::string pollBody(const std::vector<Metric>& metrics, const std::deque<LogEntry>& logs) {
  std::string body = R"({"role":"display","metrics":)" + jsonString(influxLine(kMetricsSeriesKey, metrics));
  body += R"(,"logs":[)";
  for (size_t i = 0; i < logs.size(); ++i) {
    body += (i ? "," : "");
    body += R"({"uptime_ms":)" + std::to_string(logs[i].uptimeMs) + R"(,"level":")" + levelName(logs[i].level) +
            R"(","message":)" + jsonString(logs[i].message) + "}";
  }
  body += "]}";
  return body;
}

}  // namespace

FrameClient::FrameClient(DisplayRegistrar& registrar, Http& http, Display& display, Sleeper& sleeper,
                         LogBuffer& log, Metrics& metrics)
    : registrar_(registrar), http_(http), display_(display), sleeper_(sleeper), log_(log), metrics_(metrics) {}

void FrameClient::tick() {
  if (!registered_) {
    registrar_.registerDevice();
    registered_ = true;
  }
  const std::string url = registrar_.brokerUrl() + "/api/frame";
  std::vector<Metric> metrics = metrics_.read();
  metrics.push_back({"logs_dropped", static_cast<int64_t>(log_.dropped())});
  const std::deque<LogEntry>& logs = log_.entries();
  const uint64_t sentThrough = logs.empty() ? 0 : logs.back().seq;
  const HttpResponse response = http_.request("POST", url, pollBody(metrics, logs), registrar_.secret(), etag_);
  if (!response.sent) {
    log_.warning("Couldn't fetch the frame: " + response.error);
    sleeper_.sleepSeconds(kDefaultRetryS);
    return;
  }
  // Answered as a poll should be, so the broker has the logs. Anything logged from here on (the
  // lines below included) goes with the next poll.
  const int status = response.status;
  if (status == 200 || status == 202 || status == 304 || status == 404) {
    log_.dropThrough(sentThrough);
  }
  switch (response.status) {
    case 200:
      log_.info("Got a frame (" + std::to_string(response.body.size()) + " bytes)");
      // Where the Pi's client would crash (and systemd restart it), this logs and carries on
      // polling: the next frame the broker sends is drawn as usual.
      if (display_.show(response.body)) {
        // Only a frame that's on the panel: one that couldn't be drawn is asked for again.
        etag_ = response.etag.value_or("");
      } else {
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
