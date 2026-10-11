#include "captive_probe.h"

#include <cctype>

namespace countdown {

bool isAppleProbeHost(const std::string& host) {
  std::string name;
  for (const char c : host) {
    if (c == ':') {
      break;
    }
    name += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  }
  if (name == "apple.com") {
    return true;
  }
  // The dot keeps notapple.com out.
  const std::string suffix = ".apple.com";
  return name.size() > suffix.size() && name.compare(name.size() - suffix.size(), suffix.size(), suffix) == 0;
}

}  // namespace countdown
