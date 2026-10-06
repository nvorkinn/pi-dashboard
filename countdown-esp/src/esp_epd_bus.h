#pragma once

#include <SPI.h>

#include "epd_bus.h"

// Which ESP32 GPIO each of the e-Paper HAT's wires goes to (see "Connecting the e-paper panel" in
// the README). PWR is -1 for a HAT without a PWR pin.
struct EpdPins {
  int din;
  int clk;
  int cs;
  int dc;
  int rst;
  int busy;
  int pwr;
};

// The HAT over the ESP32's second SPI bus (HSPI), as the Pi's epdconfig drives it: SPI mode 0 at
// 4 MHz, with CS, DC, RST and PWR as plain GPIOs.
class EspEpdBus : public countdown::EpdBus {
 public:
  explicit EspEpdBus(const EpdPins& pins);

  void powerOn() override;
  void powerOff() override;
  void setReset(bool high) override;
  void command(uint8_t command) override;
  void data(const uint8_t* bytes, size_t length) override;
  bool busy() override;
  void delayMs(uint32_t ms) override;
  uint32_t millis() override;

 private:
  void write(bool isData, const uint8_t* bytes, size_t length);

  EpdPins pins_;
  SPIClass spi_;
  bool spiStarted_ = false;
};
