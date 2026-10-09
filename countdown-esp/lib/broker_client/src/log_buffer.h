#pragma once

// Keeping log lines until the broker has them: each frame poll sends what's buffered, and only a
// poll the broker answers clears it.

#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>

#include "ports.h"

namespace countdown {

struct LogEntry {
  uint64_t seq;  // Counts up from 1 across the board's uptime, so a send can say how far it got.
  uint64_t uptimeMs;
  LogLevel level;
  std::string message;
};

// So a long outage can't eat the heap: past these, the oldest lines go first.
constexpr size_t kMaxLogEntries = 50;
constexpr size_t kMaxLogBytes = 8 * 1024;  // Of messages, all together
constexpr size_t kMaxLogMessageBytes = 512;

// A Log that hands every line on to `out` (Serial, on the board) and also keeps it for the broker.
class LogBuffer : public Log {
 public:
  LogBuffer(Log& out, Clock& clock);

  void write(LogLevel level, const std::string& message) override;

  // Oldest first.
  const std::deque<LogEntry>& entries() const { return entries_; }
  // Forgets the lines up to and including `seq`, once the broker has them.
  void dropThrough(uint64_t seq);
  // Lines pushed out by the limits before the broker got them, since boot.
  uint64_t dropped() const { return dropped_; }

 private:
  Log& out_;
  Clock& clock_;
  std::deque<LogEntry> entries_;
  size_t bytes_ = 0;
  uint64_t nextSeq_ = 1;
  uint64_t dropped_ = 0;
};

}  // namespace countdown
