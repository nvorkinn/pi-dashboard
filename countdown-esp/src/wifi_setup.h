#pragma once

#include "ports.h"

// Joins the Wi-Fi network saved in `store` (WIFI_SSID, WIFI_PASSWORD). If none is saved, or it can't
// be joined, opens a WiFiManager set-up portal (an open access point named countdown-XXXX) and
// saves what's entered there. Returns once connected; restarts the board if the portal times out.
void connectWifi(countdown::Store& store, countdown::Log& log);
