#pragma once

#include <string>

namespace countdown {

// `value` as a JSON string literal, quotes included. Bytes from 0x80 up pass through as they are,
// so `value` must be valid UTF-8 for the result to be valid JSON.
std::string jsonString(const std::string& value);

}  // namespace countdown
