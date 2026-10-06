#include "esp_ports.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <esp_system.h>

#include <vector>

#include "retry.h"

NvsStore::NvsStore(const char* name) { preferences_.begin(name); }

std::optional<std::string> NvsStore::get(const std::string& key) {
  if (!preferences_.isKey(key.c_str())) {
    return std::nullopt;
  }
  return std::string(preferences_.getString(key.c_str()).c_str());
}

void NvsStore::put(const std::string& key, const std::string& value) {
  preferences_.putString(key.c_str(), value.c_str());
}

namespace {

// A Stream that appends whatever HTTPClient writes to it to a vector, so a response body of any
// size (or chunked) can be read with writeToStream.
class VectorStream : public Stream {
 public:
  explicit VectorStream(std::vector<uint8_t>& out) : out_(out) {}
  size_t write(uint8_t byte) override {
    out_.push_back(byte);
    return 1;
  }
  size_t write(const uint8_t* buffer, size_t size) override {
    out_.insert(out_.end(), buffer, buffer + size);
    return size;
  }
  int available() override { return 0; }
  int read() override { return -1; }
  int peek() override { return -1; }
  void flush() override {}

 private:
  std::vector<uint8_t>& out_;
};

}  // namespace

EspHttp::EspHttp(const char* rootCerts) { client_.setCACert(rootCerts); }

countdown::HttpResponse EspHttp::request(const std::string& method, const std::string& url,
                                         const std::string& jsonBody, const std::string& bearer) {
  countdown::HttpResponse response;
  HTTPClient http;
  http.setConnectTimeout(countdown::kRequestTimeoutS * 1000);
  http.setTimeout(countdown::kRequestTimeoutS * 1000);
  if (!http.begin(client_, url.c_str())) {
    response.error = "couldn't parse " + url;
    return response;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", ("Bearer " + bearer).c_str());
  const char* collected[] = {"Retry-After"};
  http.collectHeaders(collected, 1);

  const int status = http.sendRequest(method.c_str(), reinterpret_cast<uint8_t*>(const_cast<char*>(jsonBody.data())),
                                      jsonBody.size());
  if (status < 0) {
    response.error = HTTPClient::errorToString(status).c_str();
    http.end();
    return response;
  }
  response.sent = true;
  response.status = status;
  if (http.hasHeader("Retry-After")) {
    response.retryAfter = http.header("Retry-After").c_str();
  }
  const int size = http.getSize();
  if (size != 0) {
    if (size > 0) {
      response.body.reserve(size);
    }
    VectorStream body(response.body);
    http.writeToStream(&body);
  }
  http.end();
  return response;
}

void EspRandom::fill(uint8_t* buffer, size_t length) { esp_fill_random(buffer, length); }

void DelaySleeper::sleepSeconds(int seconds) { delay(static_cast<unsigned long>(seconds) * 1000UL); }

void SerialLog::write(countdown::LogLevel level, const std::string& message) {
  const char* name = level == countdown::LogLevel::Error     ? "ERROR"
                     : level == countdown::LogLevel::Warning ? "WARNING"
                                                             : "INFO";
  Serial.printf("%s %s\n", name, message.c_str());
}
