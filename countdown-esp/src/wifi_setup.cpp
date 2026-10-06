#include "wifi_setup.h"

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>

#include <string>

namespace {

constexpr char kSsidKey[] = "WIFI_SSID";
constexpr char kPasswordKey[] = "WIFI_PASSWORD";
constexpr char kHostname[] = "countdown-esp-nikolai";
constexpr unsigned long kConnectTimeoutMs = 30 * 1000;
constexpr int kPortalTimeoutS = 5 * 60;

bool join(const std::string& ssid, const std::string& password) {
  WiFi.begin(ssid.c_str(), password.c_str());
  return WiFi.waitForConnectResult(kConnectTimeoutMs) == WL_CONNECTED;
}

// countdown- and the last two bytes of the MAC, so two boards' portals can be told apart.
String portalName() {
  String mac = WiFi.macAddress();  // AA:BB:CC:DD:EE:FF
  mac.replace(":", "");
  return "countdown-" + mac.substring(8);
}

void runPortal(countdown::Store& store, countdown::Log& log) {
  WiFiManager manager;
  manager.setConfigPortalTimeout(kPortalTimeoutS);
  const String name = portalName();
  log.info(std::string("Opening the Wi-Fi set-up portal: join ") + name.c_str() + " and browse to 192.168.4.1");
  if (!manager.startConfigPortal(name.c_str())) {
    log.error("Nobody set up Wi-Fi in time; restarting");
    ESP.restart();
  }
  store.put(kSsidKey, WiFi.SSID().c_str());
  store.put(kPasswordKey, manager.getWiFiPass().c_str());
}

}  // namespace

void connectWifi(countdown::Store& store, countdown::Log& log) {
  WiFi.setHostname(kHostname);  // before mode(), or the 2.x core ignores it
  WiFi.mode(WIFI_STA);
  // The credentials live in our NVS keys, not the Wi-Fi driver's own copy.
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);

  const auto ssid = store.get(kSsidKey);
  const auto password = store.get(kPasswordKey);
  if (ssid && password) {
    log.info("Connecting to " + *ssid);
    if (join(*ssid, *password)) {
      log.info(std::string("Connected, IP: ") + WiFi.localIP().toString().c_str());
      return;
    }
    log.warning("Couldn't connect to " + *ssid);
  } else {
    log.info("No Wi-Fi credentials saved");
  }
  runPortal(store, log);
  log.info(std::string("Connected, IP: ") + WiFi.localIP().toString().c_str());
}
