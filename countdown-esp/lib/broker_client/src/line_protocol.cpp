#include "line_protocol.h"

namespace countdown {

namespace {

// Field keys escape commas, spaces and equals signs with a backslash.
std::string fieldKey(const std::string& name) {
  std::string out;
  out.reserve(name.size());
  for (const char c : name) {
    if (c == ',' || c == ' ' || c == '=') {
      out += '\\';
    }
    out += c;
  }
  return out;
}

}  // namespace

std::string influxLine(const std::string& seriesKey, const std::vector<Metric>& metrics) {
  if (metrics.empty()) {
    return "";
  }
  std::string line = seriesKey + " ";
  for (size_t i = 0; i < metrics.size(); ++i) {
    line += (i ? "," : "") + fieldKey(metrics[i].name) + "=" + std::to_string(metrics[i].value) + "i";
  }
  return line;
}

}  // namespace countdown
