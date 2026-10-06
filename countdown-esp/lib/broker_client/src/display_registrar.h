#pragma once

// Registering with auth-broker (https://github.com/nvorkinn/auth-broker) as a display: the port of
// countdown_credentials.registration's Registrar and DisplayRegistrar. The device's identity is a
// secret kept in the Store, which is also sent as the bearer token on every request.

#include <string>

#include "ports.h"

namespace countdown {

// The Store key the device secret is kept under.
constexpr char kDeviceSecretKey[] = "device_secret";

class DisplayRegistrar {
 public:
  // Loads the device secret from `store`, or makes and saves a new one. A new secret is saved
  // before it's ever sent, so retrying a registration never makes a second identity.
  DisplayRegistrar(const std::string& brokerUrl, Store& store, Http& http, Random& random,
                   Sleeper& sleeper, Log& log);

  // Registers, retrying until the broker takes it. A display registers on every boot (the broker
  // allows it) and doesn't wait to be matched with a renderer: until it is, its frame polls
  // answer 202.
  void registerDevice();

  const std::string& brokerUrl() const { return brokerUrl_; }
  const std::string& secret() const { return secret_; }

 private:
  void newSecret();

  std::string brokerUrl_;
  Store& store_;
  Http& http_;
  Random& random_;
  Sleeper& sleeper_;
  Log& log_;
  std::string secret_;
};

}  // namespace countdown
