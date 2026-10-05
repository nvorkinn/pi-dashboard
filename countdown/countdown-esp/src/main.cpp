#include <Arduino.h>

// Most ESP32 dev boards wire their onboard LED to GPIO 2.
constexpr uint8_t kLedPin = 2;
constexpr unsigned long kBlinkIntervalMs = 1000;

void setup() {
  Serial.begin(115200);
  pinMode(kLedPin, OUTPUT);
  Serial.println("countdown-esp started");
}

void loop() {
  static unsigned long lastToggle = 0;
  static bool ledOn = false;

  const unsigned long now = millis();
  if (now - lastToggle >= kBlinkIntervalMs) {
    lastToggle = now;
    ledOn = !ledOn;
    digitalWrite(kLedPin, ledOn ? HIGH : LOW);
  }
}
