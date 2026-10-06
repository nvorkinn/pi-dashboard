#include <unity.h>

#include <vector>

#include "epd7in5_v2.h"
#include "epd_display.h"
#include "fake_bus.h"

using namespace countdown;
using namespace countdown::testing;

namespace {

struct Screen {
  FakeBus bus;
  Epd7in5V2 panel{bus};
  RecordingLog log;
  EpdDisplay display{panel, log};
};

const std::vector<uint8_t> kFrame(Epd7in5V2::kFrameBytes, 0xAA);

void test_a_frame_wakes_the_panel_draws_it_and_puts_it_to_sleep() {
  Screen s;

  TEST_ASSERT_TRUE(s.display.show(kFrame));

  std::vector<uint8_t> order;
  for (const CommandWithData& command : s.bus.commandsWithoutStatusChecks()) {
    if (command.first == 0x04 || command.first == 0x10 || command.first == 0x13 || command.first == 0x12 ||
        command.first == 0x07) {
      order.push_back(command.first);
    }
  }
  const std::vector<uint8_t> expected = {0x04, 0x10, 0x13, 0x12, 0x07};  // power on, draw, deep sleep
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected.data(), order.data(), expected.size());
  TEST_ASSERT_EQUAL(expected.size(), order.size());
  TEST_ASSERT_TRUE(s.bus.events.front().kind == Event::Kind::PowerOn);
  TEST_ASSERT_TRUE(s.bus.events.back().kind == Event::Kind::PowerOff);
  TEST_ASSERT_TRUE(s.log.lines.empty());
}

void test_a_frame_of_the_wrong_size_is_refused_without_touching_the_panel() {
  Screen s;

  TEST_ASSERT_FALSE(s.display.show(std::vector<uint8_t>(100, 0xFF)));

  TEST_ASSERT_TRUE(s.bus.events.empty());
  TEST_ASSERT_TRUE(s.log.has(LogLevel::Error, "The frame is 100 bytes; the panel takes 48000"));
}

void test_a_missing_panel_is_reported_and_nothing_is_drawn() {
  Screen s;
  s.bus.stuck = true;

  TEST_ASSERT_FALSE(s.display.show(kFrame));

  TEST_ASSERT_EQUAL(0, s.bus.count(0x10));
  TEST_ASSERT_TRUE(s.log.has(LogLevel::Error, "is it connected and powered?"));
}

void test_a_refresh_that_never_finishes_is_reported() {
  Screen s;
  s.bus.hangAfter = 0x12;

  TEST_ASSERT_FALSE(s.display.show(kFrame));

  TEST_ASSERT_EQUAL(0, s.bus.count(0x07));
  TEST_ASSERT_TRUE(s.log.has(LogLevel::Error, "still busy after drawing"));
}

void test_a_panel_that_wont_sleep_is_reported() {
  Screen s;
  s.bus.hangAfter = 0x02;

  TEST_ASSERT_FALSE(s.display.show(kFrame));

  TEST_ASSERT_TRUE(s.log.has(LogLevel::Error, "didn't go to sleep"));
}

}  // namespace

void runEpdDisplayTests() {
  RUN_TEST(test_a_frame_wakes_the_panel_draws_it_and_puts_it_to_sleep);
  RUN_TEST(test_a_frame_of_the_wrong_size_is_refused_without_touching_the_panel);
  RUN_TEST(test_a_missing_panel_is_reported_and_nothing_is_drawn);
  RUN_TEST(test_a_refresh_that_never_finishes_is_reported);
  RUN_TEST(test_a_panel_that_wont_sleep_is_reported);
}
