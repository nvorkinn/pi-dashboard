#pragma once

// A fake e-Paper HAT that records what the driver does to it, with a clock that only moves when the
// driver waits, and a BUSY line the test scripts.

#include <cstdint>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "epd_bus.h"
#include "ports.h"

namespace countdown::testing {

struct Event {
  enum class Kind { PowerOn, PowerOff, Reset, Command, Data, Delay };

  Event(Kind kind, uint32_t value = 0, std::vector<uint8_t> bytes = {})
      : kind(kind), value(value), bytes(std::move(bytes)) {}

  Kind kind;
  uint32_t value;              // Reset: high or not; Command: the byte; Delay: ms
  std::vector<uint8_t> bytes;  // Data
};

using CommandWithData = std::pair<uint8_t, std::vector<uint8_t>>;

class FakeBus : public EpdBus {
 public:
  void powerOn() override { events.push_back({Event::Kind::PowerOn}); }
  void powerOff() override { events.push_back({Event::Kind::PowerOff}); }
  void setReset(bool high) override { events.push_back({Event::Kind::Reset, high}); }
  void command(uint8_t command) override {
    events.push_back({Event::Kind::Command, command});
    if (hangAfter && *hangAfter == command) {
      stuck = true;
    }
  }
  void data(const uint8_t* bytes, size_t length) override {
    events.push_back({Event::Kind::Data, 0, std::vector<uint8_t>(bytes, bytes + length)});
  }
  bool busy() override {
    if (stuck) {
      return true;
    }
    if (busyFor > 0) {
      --busyFor;
      return true;
    }
    return false;
  }
  void delayMs(uint32_t ms) override {
    events.push_back({Event::Kind::Delay, ms});
    now += ms;
  }
  uint32_t millis() override { return now; }

  // Each command with the data bytes sent after it, in order.
  std::vector<CommandWithData> commands() const {
    std::vector<CommandWithData> result;
    for (const Event& event : events) {
      if (event.kind == Event::Kind::Command) {
        result.push_back({static_cast<uint8_t>(event.value), {}});
      } else if (event.kind == Event::Kind::Data && !result.empty()) {
        result.back().second.insert(result.back().second.end(), event.bytes.begin(), event.bytes.end());
      }
    }
    return result;
  }

  // The commands alone, without the status checks (0x71) a BUSY wait sends.
  std::vector<CommandWithData> commandsWithoutStatusChecks() const {
    std::vector<CommandWithData> result;
    for (const CommandWithData& command : commands()) {
      if (command.first != 0x71) {
        result.push_back(command);
      }
    }
    return result;
  }

  int count(uint8_t command) const {
    int n = 0;
    for (const Event& event : events) {
      n += event.kind == Event::Kind::Command && event.value == command;
    }
    return n;
  }

  // How many BUSY checks say "busy" before it releases.
  int busyFor = 0;
  // BUSY never releases: no panel, or one that isn't answering.
  bool stuck = false;
  // BUSY never releases once this command has been sent.
  std::optional<uint8_t> hangAfter;

  uint32_t now = 0;
  std::vector<Event> events;
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

}  // namespace countdown::testing
