#include "wifi_setup.h"

#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiManager.h>

#include <string>

#include "captive_probe.h"

namespace {

constexpr char kSsidKey[] = "WIFI_SSID";
constexpr char kPasswordKey[] = "WIFI_PASSWORD";
constexpr char kHostname[] = "countdown-esp-nikolai";
constexpr unsigned long kConnectTimeoutMs = 30 * 1000;
constexpr int kPortalTimeoutS = 5 * 60;

const char* statusName(wl_status_t status) {
  switch (status) {
    case WL_NO_SSID_AVAIL:
      return "network not found";
    case WL_CONNECT_FAILED:
      return "connection failed (wrong password?)";
    case WL_CONNECTION_LOST:
      return "connection lost";
    case WL_DISCONNECTED:
      return "disconnected";
    case WL_IDLE_STATUS:
      return "idle";
    default:
      return "not connected";
  }
}

// Waits out the whole timeout instead of using WiFi.waitForConnectResult(), which returns on the
// first failed attempt. Straight after boot that's often "network not found", before the first scan
// has seen the router, while auto-reconnect would have joined it a few seconds later.
bool join(const std::string& ssid, const std::string& password, countdown::Log& log) {
  WiFi.begin(ssid.c_str(), password.c_str());
  const unsigned long start = millis();
  while (millis() - start < kConnectTimeoutMs) {
    if (WiFi.status() == WL_CONNECTED) {
      return true;
    }
    delay(100);
  }
  log.warning("Couldn't connect to " + ssid + ": " + statusName(WiFi.status()));
  return false;
}

// countdown- and the last two bytes of the MAC, so two boards' portals can be told apart.
String portalName() {
  String mac = WiFi.macAddress();  // AA:BB:CC:DD:EE:FF
  mac.replace(":", "");
  return "ePaper-Dashboard-" + mac.substring(8);
}

// Answers every URL WiFiManager has no page for (phones' captive-portal checks, favicon.ico) with a
// redirect to the portal. Without it they fall through to WiFiManager's onNotFound, which redirects
// too, but only after WebServer has logged "request handler not found" for each one.
class RedirectToPortal : public RequestHandler {
 public:
  bool canHandle(HTTPMethod, String) override { return true; }
  bool handle(WebServer& server, HTTPMethod, String) override {
    server.sendHeader("Location", "http://" + WiFi.softAPIP().toString() + "/", true);
    server.send(302, "text/plain", "");
    return true;
  }
};

// Answers iOS's "is there internet?" checks with the page it expects, so it doesn't open its
// pop-up sheet (which closes when the access point goes away) and the user does set-up in Safari.
class AppleProbeSuccess : public RequestHandler {
 public:
  explicit AppleProbeSuccess(WiFiManager& manager) : manager_(manager) {}
  bool canHandle(HTTPMethod, String) override {
    return countdown::isAppleProbeHost(manager_.server->hostHeader().c_str());
  }
  bool handle(WebServer& server, HTTPMethod, String) override {
    server.send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>");
    return true;
  }

 private:
  WiFiManager& manager_;
};

// WiFiManager only listens for "scan done" in autoConnect(), which we don't use, so an async scan
// never lands in its cache and /wifi scans again, in the request. This hands it the result.
class PortalManager : public WiFiManager {
 public:
  void onScanDone(int networksFound) { WiFi_scanComplete(networksFound); }
};

// Runs on the "Saving" page (/wifisave) only. Once the board's access point is gone and the broker
// answers, the phone is back online: go there. Needing both keeps Wi-Fi Assist (iOS using mobile data
// while the access point has no internet) from sending the phone on before the board has joined. If
// the board still answers after a minute the join failed, so go back to the set-up page.
String redirectScript(const std::string& url) {
  String script = "<script>(function(){if(location.pathname!=='/wifisave')return;var u='";
  script += url.c_str();
  script += R"JS(',s=Date.now(),b=false;
function r(x){var c=new AbortController(),t=setTimeout(function(){c.abort()},1500);
return fetch(x,{mode:'no-cors',cache:'no-store',signal:c.signal}).then(function(){clearTimeout(t);return true},function(){clearTimeout(t);return false})}
setInterval(function(){if(b)return;b=true;Promise.all([r('/'),r(u)]).then(function(v){b=false;
if(!v[0]&&v[1])location.href=u;else if(v[0]&&Date.now()-s>60000)location.href='/'})},2000)})()</script>)JS";
  return script;
}

void runPortal(countdown::Store& store, countdown::Log& log, const std::string& afterSetupUrl) {
  PortalManager manager;
  // Must outlive manager: it keeps the pointer.
  const String head = redirectScript(afterSetupUrl);
  manager.setCustomHeadElement(head.c_str());
  // Runs before WiFiManager registers its own pages, so this handler is asked first.
  manager.setWebServerCallback([&manager]() { manager.server->addHandler(new AppleProbeSuccess(manager)); });
  // Verbose, not DEV: DEV logs the Wi-Fi password.
  manager.setDebugOutput(true, WM_DEBUG_VERBOSE);
  // Non-blocking, so the loop below can stop the portal as soon as Wi-Fi is up.
  manager.setConfigPortalBlocking(false);
  manager.setConfigPortalTimeout(kPortalTimeoutS);
  // Without a save timeout WiFiManager waits with WiFi.waitForConnectResult() too, so a network
  // that isn't found on the first try fails the save and the portal shows "No AP set".
  manager.setSaveConnectTimeout(kConnectTimeoutMs / 1000);
  // Scan in the background when the portal opens and when the start page is hit, so the list is
  // cached by the time the user taps "Configure WiFi" (a scan inside that request freezes the page).
  manager._preloadwifiscan = true;
  manager._asyncScan = true;
  // Fresh for the whole time the portal is open, so /wifi never has to scan itself.
  manager._scancachetime = kPortalTimeoutS * 1000;
  const wifi_event_id_t scanEvent = WiFi.onEvent(
      [&manager](arduino_event_id_t, arduino_event_info_t) { manager.onScanDone(WiFi.scanComplete()); },
      ARDUINO_EVENT_WIFI_SCAN_DONE);
  const String name = portalName();
  log.info(std::string("Opening the Wi-Fi set-up portal: join ") + name.c_str() + " and browse to 192.168.4.1");
  manager.startConfigPortal(name.c_str());
  // Added after WiFiManager's own handlers, so it only gets the URLs they don't match.
  manager.server->addHandler(new RedirectToPortal());

  while (!manager.process() && WiFi.status() != WL_CONNECTED) {
    if (!manager.getConfigPortalActive()) {
      log.error("Nobody set up Wi-Fi in time; restarting");
      ESP.restart();
    }
    delay(10);
  }
  if (manager.getConfigPortalActive()) {
    manager.stopConfigPortal();
  }
  WiFi.removeEvent(scanEvent);
  WiFi.mode(WIFI_STA);  // the portal's access point off for good
  store.put(kSsidKey, WiFi.SSID().c_str());
  store.put(kPasswordKey, manager.getWiFiPass().c_str());
  log.info(std::string("Saved Wi-Fi credentials for ") + WiFi.SSID().c_str());
}

}  // namespace

void connectWifi(countdown::Store& store, countdown::Log& log, const std::string& afterSetupUrl) {
  WiFi.setHostname(kHostname);  // before mode(), or the 2.x core ignores it
  WiFi.mode(WIFI_STA);
  // The credentials live in our NVS keys, not the Wi-Fi driver's own copy.
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);

  const auto ssid = store.get(kSsidKey);
  const auto password = store.get(kPasswordKey);
  if (ssid && password) {
    log.info("Connecting to " + *ssid);
    if (join(*ssid, *password, log)) {
      log.info(std::string("Connected, IP: ") + WiFi.localIP().toString().c_str());
      return;
    }
  } else {
    log.info("No Wi-Fi credentials saved");
  }
  runPortal(store, log, afterSetupUrl);
  log.info(std::string("Connected, IP: ") + WiFi.localIP().toString().c_str());
}
