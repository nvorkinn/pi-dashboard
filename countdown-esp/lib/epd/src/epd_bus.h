#pragma once

// The e-Paper HAT's wires, as an interface, so the panel driver is plain C++ that the native tests
// can drive with a fake. The ESP32 implementation is src/esp_epd_bus.cpp.

#include <cstddef>
#include <cstdint>

namespace countdown {

class EpdBus {
 public:
  virtual ~EpdBus() = default;

  // epdconfig.module_init(): power the HAT up and get SPI ready.
  virtual void powerOn() = 0;
  // epdconfig.module_exit(): RST and DC low, the HAT's power off.
  virtual void powerOff() = 0;

  virtual void setReset(bool high) = 0;
  // A command byte (DC low) or data (DC high), each inside its own CS low/high.
  virtual void command(uint8_t command) = 0;
  virtual void data(const uint8_t* bytes, size_t length) = 0;
  void data(uint8_t byte) { data(&byte, 1); }

  // True while the panel is busy, which it signals by holding BUSY low.
  virtual bool busy() = 0;

  virtual void delayMs(uint32_t ms) = 0;
  virtual uint32_t millis() = 0;
};

}  // namespace countdown
