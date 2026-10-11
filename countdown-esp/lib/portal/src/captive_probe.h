#pragma once

#include <string>

namespace countdown {

// True if `host` (a Host header: any case, optional ":port") is one iOS asks to find out whether a
// Wi-Fi network has internet: apple.com or any of its subdomains, such as captive.apple.com.
bool isAppleProbeHost(const std::string& host);

}  // namespace countdown
