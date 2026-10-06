#include "token.h"

#include <vector>

namespace countdown {

namespace {
constexpr char kAlphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
}  // namespace

std::string base64UrlEncode(const uint8_t* data, size_t length) {
  std::string encoded;
  encoded.reserve((length * 4 + 2) / 3);
  size_t i = 0;
  for (; i + 3 <= length; i += 3) {
    const uint32_t triple = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2];
    encoded += kAlphabet[(triple >> 18) & 0x3F];
    encoded += kAlphabet[(triple >> 12) & 0x3F];
    encoded += kAlphabet[(triple >> 6) & 0x3F];
    encoded += kAlphabet[triple & 0x3F];
  }
  const size_t remaining = length - i;
  if (remaining == 1) {
    const uint32_t triple = data[i] << 16;
    encoded += kAlphabet[(triple >> 18) & 0x3F];
    encoded += kAlphabet[(triple >> 12) & 0x3F];
  } else if (remaining == 2) {
    const uint32_t triple = (data[i] << 16) | (data[i + 1] << 8);
    encoded += kAlphabet[(triple >> 18) & 0x3F];
    encoded += kAlphabet[(triple >> 12) & 0x3F];
    encoded += kAlphabet[(triple >> 6) & 0x3F];
  }
  return encoded;
}

std::string tokenUrlsafe(Random& random, size_t nbytes) {
  std::vector<uint8_t> bytes(nbytes);
  random.fill(bytes.data(), bytes.size());
  return base64UrlEncode(bytes.data(), bytes.size());
}

}  // namespace countdown
