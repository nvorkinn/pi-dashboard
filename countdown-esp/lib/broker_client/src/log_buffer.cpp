#include "log_buffer.h"

namespace countdown {

namespace {

// `message` cut to at most `limit` bytes, backing off to the start of a UTF-8 character so the
// JSON it goes into stays valid.
std::string truncated(const std::string& message, size_t limit) {
  if (message.size() <= limit) {
    return message;
  }
  size_t end = limit;
  while (end > 0 && (static_cast<unsigned char>(message[end]) & 0xC0) == 0x80) {
    --end;
  }
  return message.substr(0, end);
}

}  // namespace

LogBuffer::LogBuffer(Log& out, Clock& clock) : out_(out), clock_(clock) {}

void LogBuffer::write(LogLevel level, const std::string& message) {
  out_.write(level, message);
  entries_.push_back({nextSeq_++, clock_.uptimeMs(), level, truncated(message, kMaxLogMessageBytes)});
  bytes_ += entries_.back().message.size();
  while (entries_.size() > kMaxLogEntries || bytes_ > kMaxLogBytes) {
    bytes_ -= entries_.front().message.size();
    entries_.pop_front();
    ++dropped_;
  }
}

void LogBuffer::dropThrough(uint64_t seq) {
  while (!entries_.empty() && entries_.front().seq <= seq) {
    bytes_ -= entries_.front().message.size();
    entries_.pop_front();
  }
}

}  // namespace countdown
