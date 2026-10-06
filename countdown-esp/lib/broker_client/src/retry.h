#pragma once

#include <optional>
#include <string>

namespace countdown {

// How long to wait when the broker doesn't say (no Retry-After) or can't be reached.
constexpr int kDefaultRetryS = 60;
// So a stalled connection fails (and is retried) instead of hanging the wait.
constexpr int kRequestTimeoutS = 10;

// The Retry-After header's delay in seconds, or kDefaultRetryS when it's missing or isn't a
// whole number of seconds (an HTTP date, say).
int retryAfterSeconds(const std::optional<std::string>& header);

}  // namespace countdown
