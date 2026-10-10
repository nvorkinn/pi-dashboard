#pragma once

// What the broker client needs from the board, as interfaces, so the client itself is plain C++
// that the native tests can drive with fakes. The ESP32 implementations are in src/.

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace countdown {

struct HttpResponse {
  // False when no response came back at all (no network, DNS, TLS or a timeout): the
  // equivalent of requests raising a RequestException. `error` then says why.
  bool sent = false;
  std::string error;
  int status = 0;
  std::optional<std::string> retryAfter;
  // The ETag header as the server sent it, quotes and all.
  std::optional<std::string> etag;
  std::vector<uint8_t> body;
};

class Http {
 public:
  virtual ~Http() = default;
  // Sends `jsonBody` as application/json, with `bearer` as the Authorization bearer token and, unless
  // it's empty, `ifNoneMatch` as the If-None-Match header.
  virtual HttpResponse request(const std::string& method, const std::string& url, const std::string& jsonBody,
                               const std::string& bearer, const std::string& ifNoneMatch) = 0;
};

// Survives reboots: NVS on the board.
class Store {
 public:
  virtual ~Store() = default;
  virtual std::optional<std::string> get(const std::string& key) = 0;
  virtual void put(const std::string& key, const std::string& value) = 0;
};

class Random {
 public:
  virtual ~Random() = default;
  // Cryptographically secure bytes.
  virtual void fill(uint8_t* buffer, size_t length) = 0;
};

class Sleeper {
 public:
  virtual ~Sleeper() = default;
  virtual void sleepSeconds(int seconds) = 0;
};

class Clock {
 public:
  virtual ~Clock() = default;
  // Milliseconds since boot. The board has no wall clock to stamp logs with.
  virtual uint64_t uptimeMs() = 0;
};

struct Metric {
  std::string name;
  int64_t value;
};

// Readings about the board itself (heap, Wi-Fi signal, ...), sent with every frame poll.
class Metrics {
 public:
  virtual ~Metrics() = default;
  virtual std::vector<Metric> read() = 0;
};

enum class LogLevel { Info, Warning, Error };

class Log {
 public:
  virtual ~Log() = default;
  virtual void write(LogLevel level, const std::string& message) = 0;

  void info(const std::string& message) { write(LogLevel::Info, message); }
  void warning(const std::string& message) { write(LogLevel::Warning, message); }
  void error(const std::string& message) { write(LogLevel::Error, message); }
};

// Where frames are drawn: the e-paper panel on the board.
class Display {
 public:
  virtual ~Display() = default;
  // Draws a frame from the broker; false if it couldn't (the implementation logs why).
  virtual bool show(const std::vector<uint8_t>& frame) = 0;
};

}  // namespace countdown
