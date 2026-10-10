#include <unity.h>

#include <cstdint>
#include <string>

#include "fakes.h"
#include "line_protocol.h"

using namespace countdown;

namespace {

void test_metrics_are_integer_fields_after_the_series_key() {
  TEST_ASSERT_EQUAL_STD_STRING("esp32,device_id={device_id} free_heap=182344i,wifi_rssi=-61i",
                               influxLine("esp32,device_id={device_id}", {{"free_heap", 182344}, {"wifi_rssi", -61}}));
}

void test_large_values_keep_every_digit() {
  TEST_ASSERT_EQUAL_STD_STRING("m big=9223372036854775807i", influxLine("m", {{"big", INT64_MAX}}));
}

void test_field_keys_are_escaped() {
  TEST_ASSERT_EQUAL_STD_STRING(R"(m a\,b\ c\=d=1i)", influxLine("m", {{"a,b c=d", 1}}));
}

void test_no_metrics_is_no_line() { TEST_ASSERT_EQUAL_STD_STRING("", influxLine("m", {})); }

}  // namespace

void runLineProtocolTests() {
  RUN_TEST(test_metrics_are_integer_fields_after_the_series_key);
  RUN_TEST(test_large_values_keep_every_digit);
  RUN_TEST(test_field_keys_are_escaped);
  RUN_TEST(test_no_metrics_is_no_line);
}
