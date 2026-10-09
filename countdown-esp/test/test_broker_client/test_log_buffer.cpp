#include <unity.h>

#include <string>

#include "fakes.h"
#include "json.h"
#include "log_buffer.h"

using namespace countdown;
using namespace countdown::testing;

namespace {

struct Buffer {
  RecordingLog out;
  FakeClock clock;
  LogBuffer logs{out, clock};
};

void test_lines_are_passed_on_and_kept() {
  Buffer b;
  b.clock.now = 42;

  b.logs.warning("careful");

  TEST_ASSERT_TRUE(b.out.has(LogLevel::Warning, "careful"));
  TEST_ASSERT_EQUAL(1, b.logs.entries().size());
  const LogEntry& entry = b.logs.entries().front();
  TEST_ASSERT_EQUAL(1, entry.seq);
  TEST_ASSERT_EQUAL(42, entry.uptimeMs);
  TEST_ASSERT_TRUE(entry.level == LogLevel::Warning);
  TEST_ASSERT_EQUAL_STD_STRING("careful", entry.message);
}

void test_drop_through_forgets_up_to_and_including_seq() {
  Buffer b;
  b.logs.info("one");
  b.logs.info("two");
  b.logs.info("three");

  b.logs.dropThrough(2);

  TEST_ASSERT_EQUAL(1, b.logs.entries().size());
  TEST_ASSERT_EQUAL_STD_STRING("three", b.logs.entries().front().message);
  TEST_ASSERT_EQUAL(0, b.logs.dropped());  // Delivered, not dropped
}

void test_past_the_entry_limit_the_oldest_go_and_are_counted() {
  Buffer b;
  for (size_t i = 0; i < kMaxLogEntries + 3; ++i) {
    b.logs.info(std::to_string(i));
  }

  TEST_ASSERT_EQUAL(kMaxLogEntries, b.logs.entries().size());
  TEST_ASSERT_EQUAL_STD_STRING("3", b.logs.entries().front().message);
  TEST_ASSERT_EQUAL(3, b.logs.dropped());
}

void test_past_the_byte_limit_the_oldest_go() {
  Buffer b;
  const std::string line(kMaxLogMessageBytes, 'x');
  const size_t fit = kMaxLogBytes / kMaxLogMessageBytes;
  for (size_t i = 0; i < fit + 1; ++i) {
    b.logs.info(line);
  }

  TEST_ASSERT_EQUAL(fit, b.logs.entries().size());
  TEST_ASSERT_EQUAL(1, b.logs.dropped());
  b.logs.dropThrough(b.logs.entries().back().seq);
  b.logs.info(line);  // Room again once delivered
  TEST_ASSERT_EQUAL(1, b.logs.dropped());
}

void test_long_messages_are_cut_at_a_character_boundary() {
  Buffer b;
  // "é" is two bytes; the limit falls between them.
  b.logs.info(std::string(kMaxLogMessageBytes - 1, 'x') + "é");

  const std::string& kept = b.logs.entries().front().message;
  TEST_ASSERT_EQUAL(kMaxLogMessageBytes - 1, kept.size());
  TEST_ASSERT_TRUE(b.out.has(LogLevel::Info, "é"));  // Serial still gets all of it
}

void test_json_string_escapes() {
  TEST_ASSERT_EQUAL_STD_STRING(R"("plain")", jsonString("plain"));
  TEST_ASSERT_EQUAL_STD_STRING(R"("a\"b\\c")", jsonString("a\"b\\c"));
  TEST_ASSERT_EQUAL_STD_STRING(R"("\n\r\t\u0001")", jsonString("\n\r\t\x01"));
  TEST_ASSERT_EQUAL_STD_STRING("\"é\"", jsonString("é"));
}

}  // namespace

void runLogBufferTests() {
  RUN_TEST(test_lines_are_passed_on_and_kept);
  RUN_TEST(test_drop_through_forgets_up_to_and_including_seq);
  RUN_TEST(test_past_the_entry_limit_the_oldest_go_and_are_counted);
  RUN_TEST(test_past_the_byte_limit_the_oldest_go);
  RUN_TEST(test_long_messages_are_cut_at_a_character_boundary);
  RUN_TEST(test_json_string_escapes);
}
