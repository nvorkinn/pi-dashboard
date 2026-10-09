#include "json.h"

#include <cstdio>

namespace countdown {

std::string jsonString(const std::string& value) {
  std::string out = "\"";
  out.reserve(value.size() + 2);
  for (const char c : value) {
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      default:
        if (static_cast<unsigned char>(c) < 0x20) {
          char escaped[7];
          std::snprintf(escaped, sizeof(escaped), "\\u%04x", static_cast<unsigned char>(c));
          out += escaped;
        } else {
          out += c;
        }
    }
  }
  out += '"';
  return out;
}

}  // namespace countdown
