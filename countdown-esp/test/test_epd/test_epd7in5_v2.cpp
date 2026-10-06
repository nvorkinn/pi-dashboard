#include <unity.h>

#include <vector>

#include "epd7in5_v2.h"
#include "fake_bus.h"

using namespace countdown;
using namespace countdown::testing;

namespace {

using Kind = Event::Kind;

std::vector<uint8_t> patternFrame() {
  std::vector<uint8_t> frame(Epd7in5V2::kFrameBytes);
  for (size_t i = 0; i < frame.size(); ++i) {
    frame[i] = static_cast<uint8_t>(i * 7);
  }
  return frame;
}

void assertCommands(const std::vector<CommandWithData>& expected, const std::vector<CommandWithData>& actual) {
  TEST_ASSERT_EQUAL(expected.size(), actual.size());
  for (size_t i = 0; i < expected.size(); ++i) {
    TEST_ASSERT_EQUAL_HEX8(expected[i].first, actual[i].first);
    TEST_ASSERT_EQUAL(expected[i].second.size(), actual[i].second.size());
    if (!expected[i].second.empty()) {
      TEST_ASSERT_EQUAL_HEX8_ARRAY(expected[i].second.data(), actual[i].second.data(), expected[i].second.size());
    }
  }
}

void assertLastEventIsPowerOff(const FakeBus& bus) {
  TEST_ASSERT_TRUE(bus.events.back().kind == Kind::PowerOff);
}

void test_init_sends_the_python_drivers_commands() {
  FakeBus bus;
  Epd7in5V2 panel(bus);

  TEST_ASSERT_TRUE(panel.init());

  // epd7in5_V2.py's init(), byte for byte
  assertCommands(
      {
          {0x06, {0x17, 0x17, 0x28, 0x17}},
          {0x01, {0x07, 0x07, 0x28, 0x17}},
          {0x04, {}},
          {0x71, {}},
          {0x00, {0x1F}},
          {0x61, {0x03, 0x20, 0x01, 0xE0}},
          {0x15, {0x00}},
          {0x50, {0x10, 0x07}},
          {0x60, {0x22}},
      },
      bus.commands());
}

void test_init_powers_up_and_resets_the_panel_first() {
  FakeBus bus;
  Epd7in5V2 panel(bus);

  panel.init();

  const std::vector<Event>& e = bus.events;
  TEST_ASSERT_TRUE(e[0].kind == Kind::PowerOn);
  TEST_ASSERT_TRUE(e[1].kind == Kind::Reset && e[1].value == 1);
  TEST_ASSERT_TRUE(e[2].kind == Kind::Delay && e[2].value == 20);
  TEST_ASSERT_TRUE(e[3].kind == Kind::Reset && e[3].value == 0);
  TEST_ASSERT_TRUE(e[4].kind == Kind::Delay && e[4].value == 2);
  TEST_ASSERT_TRUE(e[5].kind == Kind::Reset && e[5].value == 1);
  TEST_ASSERT_TRUE(e[6].kind == Kind::Delay && e[6].value == 20);
  TEST_ASSERT_TRUE(e[7].kind == Kind::Command && e[7].value == 0x06);
}

void test_init_waits_for_the_power_on_handshake() {
  FakeBus bus;
  bus.busyFor = 3;
  Epd7in5V2 panel(bus);

  TEST_ASSERT_TRUE(panel.init());

  // One status check, then one more every 20 ms until BUSY releases
  TEST_ASSERT_EQUAL(4, bus.count(0x71));
  TEST_ASSERT_EQUAL(20 + 2 + 20 + 100 + 3 * 20 + 20, bus.now);
}

void test_init_gives_up_on_a_panel_that_never_answers() {
  FakeBus bus;
  bus.stuck = true;
  Epd7in5V2 panel(bus);

  TEST_ASSERT_FALSE(panel.init());

  TEST_ASSERT_EQUAL(0, bus.count(0x00));  // no PANEL SETTING after a failed POWER ON
  const uint32_t waited = bus.now - (20 + 2 + 20 + 100);
  TEST_ASSERT_GREATER_THAN(Epd7in5V2::kPowerOnTimeoutMs, waited);
  TEST_ASSERT_LESS_OR_EQUAL(Epd7in5V2::kPowerOnTimeoutMs + 20, waited);
  assertLastEventIsPowerOff(bus);
}

void test_display_sends_the_frame_inverted_then_as_is_then_refreshes() {
  FakeBus bus;
  Epd7in5V2 panel(bus);
  const std::vector<uint8_t> frame = patternFrame();
  std::vector<uint8_t> inverted(frame.size());
  for (size_t i = 0; i < frame.size(); ++i) {
    inverted[i] = static_cast<uint8_t>(~frame[i]);
  }

  TEST_ASSERT_TRUE(panel.display(frame.data()));

  const std::vector<CommandWithData> commands = bus.commandsWithoutStatusChecks();
  TEST_ASSERT_EQUAL(3, commands.size());
  TEST_ASSERT_EQUAL_HEX8(0x10, commands[0].first);
  TEST_ASSERT_EQUAL(Epd7in5V2::kFrameBytes, commands[0].second.size());
  TEST_ASSERT_EQUAL_HEX8_ARRAY(inverted.data(), commands[0].second.data(), inverted.size());
  TEST_ASSERT_EQUAL_HEX8(0x13, commands[1].first);
  TEST_ASSERT_EQUAL(Epd7in5V2::kFrameBytes, commands[1].second.size());
  TEST_ASSERT_EQUAL_HEX8_ARRAY(frame.data(), commands[1].second.data(), frame.size());
  TEST_ASSERT_EQUAL_HEX8(0x12, commands[2].first);
  TEST_ASSERT_EQUAL(1, bus.count(0x71));
}

void test_display_sends_the_inverted_copy_in_small_pieces() {
  FakeBus bus;
  Epd7in5V2 panel(bus);
  const std::vector<uint8_t> frame = patternFrame();

  panel.display(frame.data());

  size_t largest = 0;
  for (const Event& event : bus.events) {
    if (event.kind == Kind::Data && event.bytes.size() != Epd7in5V2::kFrameBytes && event.bytes.size() > largest) {
      largest = event.bytes.size();
    }
  }
  TEST_ASSERT_EQUAL(1024, largest);
}

void test_display_waits_up_to_a_minute_for_the_refresh() {
  FakeBus bus;
  bus.hangAfter = 0x12;
  Epd7in5V2 panel(bus);
  const std::vector<uint8_t> frame = patternFrame();

  TEST_ASSERT_FALSE(panel.display(frame.data()));

  const uint32_t waited = bus.now - 100;
  TEST_ASSERT_GREATER_THAN(Epd7in5V2::kBusyTimeoutMs, waited);
  TEST_ASSERT_LESS_OR_EQUAL(Epd7in5V2::kBusyTimeoutMs + 20, waited);
  assertLastEventIsPowerOff(bus);
}

void test_sleep_powers_the_panel_down_then_the_hat() {
  FakeBus bus;
  Epd7in5V2 panel(bus);

  TEST_ASSERT_TRUE(panel.sleep());

  assertCommands(
      {
          {0x50, {0xF7}},
          {0x02, {}},
          {0x71, {}},
          {0x07, {0xA5}},
      },
      bus.commands());
  const std::vector<Event>& e = bus.events;
  TEST_ASSERT_TRUE(e[e.size() - 2].kind == Kind::Delay && e[e.size() - 2].value == 2000);
  assertLastEventIsPowerOff(bus);
}

void test_sleep_gives_up_if_the_panel_never_powers_off() {
  FakeBus bus;
  bus.hangAfter = 0x02;
  Epd7in5V2 panel(bus);

  TEST_ASSERT_FALSE(panel.sleep());

  TEST_ASSERT_EQUAL(0, bus.count(0x07));  // no DEEP SLEEP
  assertLastEventIsPowerOff(bus);
}

}  // namespace

void runEpd7in5V2Tests() {
  RUN_TEST(test_init_sends_the_python_drivers_commands);
  RUN_TEST(test_init_powers_up_and_resets_the_panel_first);
  RUN_TEST(test_init_waits_for_the_power_on_handshake);
  RUN_TEST(test_init_gives_up_on_a_panel_that_never_answers);
  RUN_TEST(test_display_sends_the_frame_inverted_then_as_is_then_refreshes);
  RUN_TEST(test_display_sends_the_inverted_copy_in_small_pieces);
  RUN_TEST(test_display_waits_up_to_a_minute_for_the_refresh);
  RUN_TEST(test_sleep_powers_the_panel_down_then_the_hat);
  RUN_TEST(test_sleep_gives_up_if_the_panel_never_powers_off);
}
