#pragma once

// Fakes of the ports in ports.h, scripted by each test and recording what the code under test did.

#include <unity.h>

#include <deque>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "display_registrar.h"
#include "log_buffer.h"
#include "ports.h"

namespace countdown::testing {

struct SentRequest {
  std::string method;
  std::string url;
  std::string body;
  std::string bearer;
  std::string ifNoneMatch;
  // What the Store held as the device secret when the request went out.
  std::optional<std::string> storedSecret;
};

class MapStore : public Store {
 public:
  std::optional<std::string> get(const std::string& key) override {
    const auto it = values.find(key);
    if (it == values.end()) {
      return std::nullopt;
    }
    return it->second;
  }
  void put(const std::string& key, const std::string& value) override { values[key] = value; }

  std::map<std::string, std::string> values;
};

class FakeHttp : public Http {
 public:
  explicit FakeHttp(Store& store) : store_(store) {}

  HttpResponse request(const std::string& method, const std::string& url, const std::string& jsonBody,
                       const std::string& bearer, const std::string& ifNoneMatch) override {
    requests.push_back({method, url, jsonBody, bearer, ifNoneMatch, store_.get(kDeviceSecretKey)});
    TEST_ASSERT_FALSE_MESSAGE(responses.empty(), "A request the test didn't script a response for");
    HttpResponse response = responses.front();
    responses.pop_front();
    return response;
  }

  void reply(int status, std::optional<std::string> retryAfter = std::nullopt, const std::string& body = "",
             std::optional<std::string> etag = std::nullopt) {
    HttpResponse response;
    response.sent = true;
    response.status = status;
    response.retryAfter = std::move(retryAfter);
    response.etag = std::move(etag);
    response.body.assign(body.begin(), body.end());
    responses.push_back(response);
  }

  void fail(const std::string& error) {
    HttpResponse response;
    response.error = error;
    responses.push_back(response);
  }

  std::deque<HttpResponse> responses;
  std::vector<SentRequest> requests;

 private:
  Store& store_;
};

// Counts up from 0 across calls, so every token it makes is different and known in advance.
class CountingRandom : public Random {
 public:
  void fill(uint8_t* buffer, size_t length) override {
    for (size_t i = 0; i < length; ++i) {
      buffer[i] = next++;
    }
  }

  uint8_t next = 0;
};

class RecordingSleeper : public Sleeper {
 public:
  void sleepSeconds(int seconds) override { sleeps.push_back(seconds); }

  std::vector<int> sleeps;
};

class RecordingLog : public Log {
 public:
  void write(LogLevel level, const std::string& message) override { lines.emplace_back(level, message); }

  bool has(LogLevel level, const std::string& fragment) const {
    for (const auto& [lineLevel, message] : lines) {
      if (lineLevel == level && message.find(fragment) != std::string::npos) {
        return true;
      }
    }
    return false;
  }

  std::vector<std::pair<LogLevel, std::string>> lines;
};

// Records the frames it's asked to draw; `succeeds` says whether drawing works.
class FakeDisplay : public Display {
 public:
  bool show(const std::vector<uint8_t>& frame) override {
    shown.push_back(frame);
    return succeeds;
  }

  bool succeeds = true;
  std::vector<std::vector<uint8_t>> shown;
};

// Stands still unless a test moves it.
class FakeClock : public Clock {
 public:
  uint64_t uptimeMs() override { return now; }

  uint64_t now = 0;
};

class FakeMetrics : public Metrics {
 public:
  std::vector<Metric> read() override { return readings; }

  std::vector<Metric> readings;
};

// What CountingRandom's first and second 24 bytes encode to, from Python:
// base64.urlsafe_b64encode(bytes(range(24))).rstrip(b"=")
constexpr char kFirstToken[] = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYX";
constexpr char kSecondToken[] = "GBkaGxwdHh8gISIjJCUmJygpKissLS4v";

constexpr char kBrokerUrl[] = "https://broker.example";
constexpr char kRegisterUrl[] = "https://broker.example/api/devices/register";
constexpr char kFrameUrl[] = "https://broker.example/api/frame";

// Everything a DisplayRegistrar or FrameClient talks to, wired together.
struct Board {
  MapStore store;
  FakeHttp http{store};
  CountingRandom random;
  FakeDisplay display;
  RecordingSleeper sleeper;
  RecordingLog log;
  FakeClock clock;
  FakeMetrics metrics;
  // What the code under test logs through, as on the board: it passes every line on to `log`.
  LogBuffer logs{log, clock};

  DisplayRegistrar registrar(const std::string& brokerUrl = kBrokerUrl) {
    return DisplayRegistrar(brokerUrl, store, http, random, sleeper, logs);
  }
};

}  // namespace countdown::testing

#define TEST_ASSERT_EQUAL_STD_STRING(expected, actual) \
  TEST_ASSERT_EQUAL_STRING(std::string(expected).c_str(), std::string(actual).c_str())
