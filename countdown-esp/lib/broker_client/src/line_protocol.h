#pragma once

#include <string>
#include <vector>

#include "ports.h"

namespace countdown {

// One InfluxDB Line Protocol line of integer fields, with no timestamp, so whoever receives it
// stamps it: `seriesKey field=1i,other=-2i`. `seriesKey` (the measurement and any tags) is
// written as given. Empty if there are no metrics, since a line needs at least one field.
std::string influxLine(const std::string& seriesKey, const std::vector<Metric>& metrics);

}  // namespace countdown
