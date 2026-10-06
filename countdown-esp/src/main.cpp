#include <Arduino.h>

#include "display_registrar.h"
#include "epd7in5_v2.h"
#include "epd_display.h"
#include "esp_epd_bus.h"
#include "esp_ports.h"
#include "frame_client.h"
#include "root_certs.h"
#include "wifi_setup.h"

#ifndef BROKER_URL
#error "BROKER_URL isn't set: it comes from build_flags in platformio.ini"
#endif
#if !defined(EPD_PIN_DIN) || !defined(EPD_PIN_CLK) || !defined(EPD_PIN_CS) || !defined(EPD_PIN_DC) || \
    !defined(EPD_PIN_RST) || !defined(EPD_PIN_BUSY) || !defined(EPD_PIN_PWR)
#error "The e-paper panel's pins (EPD_PIN_*) come from build_flags in platformio.ini"
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
  static EspEpdBus epdBus({EPD_PIN_DIN, EPD_PIN_CLK, EPD_PIN_CS, EPD_PIN_DC, EPD_PIN_RST, EPD_PIN_BUSY, EPD_PIN_PWR});
  static countdown::Epd7in5V2 panel(epdBus);
  static countdown::EpdDisplay display(panel, log);
  static countdown::FrameClient frameClient(registrar, http, display, sleeper, log);
  client = &frameClient;
}

void loop() { client->tick(); }
