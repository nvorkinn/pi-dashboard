#include <Arduino.h>

#include "display_registrar.h"
#include "esp_ports.h"
#include "frame_client.h"
#include "root_certs.h"
#include "wifi_setup.h"

#ifndef BROKER_URL
#error "BROKER_URL isn't set: it comes from build_flags in platformio.ini"
#endif

namespace {
constexpr char kNvsNamespace[] = "countdown";

countdown::FrameClient* client = nullptr;
}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.println("countdown-esp started");

  static NvsStore store(kNvsNamespace);
  static SerialLog log;
  connectWifi(store, log);

  // Made after Wi-Fi is up, so a new device secret comes from the RNG at its most random.
  static EspHttp http(kBrokerRootCerts);
  static EspRandom random;
  static DelaySleeper sleeper;
  static countdown::DisplayRegistrar registrar(BROKER_URL, store, http, random, sleeper, log);
  static countdown::FrameClient frameClient(registrar, http, sleeper, log);
  client = &frameClient;
}

void loop() { client->tick(); }
