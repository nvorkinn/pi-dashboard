#pragma once

// The ESP32 implementations of lib/broker_client's ports.

#include <Preferences.h>
#include <WiFiClientSecure.h>

#include <optional>
#include <string>
#include <vector>

#include "ports.h"

// NVS, under one namespace.
class NvsStore : public countdown::Store {
 public:
  explicit NvsStore(const char* name);
  std::optional<std::string> get(const std::string& key) override;
  void put(const std::string& key, const std::string& value) override;

 private:
  Preferences preferences_;
};

// HTTPS, trusting only `rootCerts` (PEM, one or more).
class EspHttp : public countdown::Http {
 public:
  explicit EspHttp(const char* rootCerts);
  countdown::HttpResponse request(const std::string& method, const std::string& url,
                                  const std::string& jsonBody, const std::string& bearer) override;

 private:
  WiFiClientSecure client_;
};

// The hardware RNG: cryptographically secure while Wi-Fi (or Bluetooth) is on.
class EspRandom : public countdown::Random {
 public:
  void fill(uint8_t* buffer, size_t length) override;
};

class DelaySleeper : public countdown::Sleeper {
 public:
  void sleepSeconds(int seconds) override;
};

// esp_timer's 64-bit microseconds, so it doesn't wrap after 49 days as millis() does.
class EspClock : public countdown::Clock {
 public:
  uint64_t uptimeMs() override;
};

// Uptime, heap, PSRAM, the Wi-Fi signal and why the board last reset.
class EspMetrics : public countdown::Metrics {
 public:
  std::vector<countdown::Metric> read() override;
};

class SerialLog : public countdown::Log {
 public:
  void write(countdown::LogLevel level, const std::string& message) override;
};
