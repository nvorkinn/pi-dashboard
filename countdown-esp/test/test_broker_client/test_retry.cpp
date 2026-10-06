#include <unity.h>

#include "retry.h"

using namespace countdown;

namespace {

void test_retry_after_is_the_headers_seconds() {
  TEST_ASSERT_EQUAL(5, retryAfterSeconds("5"));
  TEST_ASSERT_EQUAL(0, retryAfterSeconds("0"));
  TEST_ASSERT_EQUAL(3600, retryAfterSeconds("3600"));
}

void test_retry_after_defaults_when_missing() {
  TEST_ASSERT_EQUAL(kDefaultRetryS, retryAfterSeconds(std::nullopt));
  TEST_ASSERT_EQUAL(kDefaultRetryS, retryAfterSeconds(""));
}

void test_retry_after_defaults_when_not_whole_seconds() {
  TEST_ASSERT_EQUAL(kDefaultRetryS, retryAfterSeconds("abc"));
  TEST_ASSERT_EQUAL(kDefaultRetryS, retryAfterSeconds("-5"));
  TEST_ASSERT_EQUAL(kDefaultRetryS, retryAfterSeconds("1.5"));
  TEST_ASSERT_EQUAL(kDefaultRetryS, retryAfterSeconds("Wed, 21 Oct 2026 07:28:00 GMT"));
}

void test_retry_after_defaults_when_too_long_to_be_sane() {
  TEST_ASSERT_EQUAL(kDefaultRetryS, retryAfterSeconds("99999999999999999999"));
}

}  // namespace

void runRetryTests() {
  RUN_TEST(test_retry_after_is_the_headers_seconds);
  RUN_TEST(test_retry_after_defaults_when_missing);
  RUN_TEST(test_retry_after_defaults_when_not_whole_seconds);
  RUN_TEST(test_retry_after_defaults_when_too_long_to_be_sane);
}
