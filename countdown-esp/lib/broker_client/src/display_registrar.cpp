#include "display_registrar.h"

#include "retry.h"
#include "token.h"

namespace countdown {

DisplayRegistrar::DisplayRegistrar(const std::string& brokerUrl, Store& store, Http& http,
                                   Random& random, Sleeper& sleeper, Log& log)
    : brokerUrl_(brokerUrl), store_(store), http_(http), random_(random), sleeper_(sleeper), log_(log) {
  while (!brokerUrl_.empty() && brokerUrl_.back() == '/') {
    brokerUrl_.pop_back();
  }
  secret_ = store_.get(kDeviceSecretKey).value_or("");
  if (secret_.empty()) {
    newSecret();
  }
}

void DisplayRegistrar::registerDevice() {
  const std::string url = brokerUrl_ + "/api/devices/register";
  while (true) {
    // The secret is URL-safe base64, so it needs no escaping.
    const std::string body = R"({"role":"display","secret":")" + secret_ + R"("})";
    const HttpResponse response = http_.request("POST", url, body, secret_, "");
    if (!response.sent) {
      log_.warning("Couldn't register with the broker: " + response.error);
      sleeper_.sleepSeconds(kDefaultRetryS);
      continue;
    }
    int delay = kDefaultRetryS;
    switch (response.status) {
      case 200:
      case 201:
      case 202:  // Not matched with a renderer yet, which a display doesn't wait for
        log_.info("Registered with the broker");
        return;
      case 429:
      case 503:
        delay = retryAfterSeconds(response.retryAfter);
        break;
      case 409:
        log_.warning("The secret is registered with the other role; registering a new one");
        newSecret();
        continue;
      case 400:
        log_.error("The broker rejected the registration: " +
                   std::string(response.body.begin(), response.body.end()));
        break;
      default:
        log_.warning("Unexpected " + std::to_string(response.status) + " from " + url);
        break;
    }
    sleeper_.sleepSeconds(delay);
  }
}

void DisplayRegistrar::newSecret() {
  secret_ = tokenUrlsafe(random_);
  store_.put(kDeviceSecretKey, secret_);
}

}  // namespace countdown
