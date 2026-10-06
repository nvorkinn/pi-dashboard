#include "retry.h"

#include <cctype>
#include <string>

namespace countdown {

namespace {
// Long enough for any sane delay, short enough that std::stoi can't overflow.
constexpr size_t kMaxDigits = 9;
}  // namespace

int retryAfterSeconds(const std::optional<std::string>& header) {
  if (!header || header->empty() || header->size() > kMaxDigits) {
    return kDefaultRetryS;
  }
  for (const char c : *header) {
    if (!std::isdigit(static_cast<unsigned char>(c))) {
      return kDefaultRetryS;
    }
  }
  return std::stoi(*header);
}

}  // namespace countdown
