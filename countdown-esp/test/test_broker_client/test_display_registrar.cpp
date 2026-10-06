#include <unity.h>

#include <string>
#include <vector>

#include "display_registrar.h"
#include "fakes.h"
#include "retry.h"

using namespace countdown;
using namespace countdown::testing;

namespace {

std::string registerBody(const std::string& secret) {
  return R"({"role":"display","secret":")" + secret + R"("})";
}

void test_a_new_device_saves_its_secret_before_sending_it() {
  Board board;
  board.http.reply(201);

  board.registrar().registerDevice();

  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, board.store.values[kDeviceSecretKey]);
  TEST_ASSERT_EQUAL(1, board.http.requests.size());
  const SentRequest& sent = board.http.requests[0];
  TEST_ASSERT_TRUE(sent.storedSecret.has_value());
  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, *sent.storedSecret);
}

void test_it_posts_the_display_role_and_secret_with_the_secret_as_bearer() {
  Board board;
  board.http.reply(201);

  board.registrar().registerDevice();

  const SentRequest& sent = board.http.requests[0];
  TEST_ASSERT_EQUAL_STD_STRING("POST", sent.method);
  TEST_ASSERT_EQUAL_STD_STRING(kRegisterUrl, sent.url);
  TEST_ASSERT_EQUAL_STD_STRING(registerBody(kFirstToken), sent.body);
  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, sent.bearer);
}

void test_a_saved_secret_is_reused_and_registered_again() {
  Board board;
  board.store.values[kDeviceSecretKey] = "shh";
  board.http.reply(200);

  DisplayRegistrar registrar = board.registrar();
  registrar.registerDevice();

  TEST_ASSERT_EQUAL_STD_STRING("shh", registrar.secret());
  TEST_ASSERT_EQUAL(0, board.random.next);
  TEST_ASSERT_EQUAL_STD_STRING(registerBody("shh"), board.http.requests[0].body);
}

void test_an_empty_saved_secret_is_replaced() {
  Board board;
  board.store.values[kDeviceSecretKey] = "";
  board.http.reply(201);

  board.registrar().registerDevice();

  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, board.store.values[kDeviceSecretKey]);
}

void test_trailing_slashes_are_dropped_from_the_broker_url() {
  Board board;
  board.http.reply(201);

  DisplayRegistrar registrar = board.registrar("https://broker.example//");
  registrar.registerDevice();

  TEST_ASSERT_EQUAL_STD_STRING(kBrokerUrl, registrar.brokerUrl());
  TEST_ASSERT_EQUAL_STD_STRING(kRegisterUrl, board.http.requests[0].url);
}

void test_it_goes_straight_on_when_the_broker_takes_it(int status) {
  Board board;
  board.http.reply(status);

  board.registrar().registerDevice();

  TEST_ASSERT_EQUAL(1, board.http.requests.size());
  TEST_ASSERT_TRUE(board.sleeper.sleeps.empty());
  TEST_ASSERT_TRUE(board.log.has(LogLevel::Info, "Registered"));
}

void test_200_registers() { test_it_goes_straight_on_when_the_broker_takes_it(200); }
void test_201_registers() { test_it_goes_straight_on_when_the_broker_takes_it(201); }
// A display doesn't wait to be matched with a renderer.
void test_202_registers() { test_it_goes_straight_on_when_the_broker_takes_it(202); }

void test_it_waits_as_long_as_the_broker_asks(int status) {
  Board board;
  board.http.reply(status, "17");
  board.http.reply(201);

  board.registrar().registerDevice();

  TEST_ASSERT_EQUAL(2, board.http.requests.size());
  TEST_ASSERT_EQUAL(1, board.sleeper.sleeps.size());
  TEST_ASSERT_EQUAL(17, board.sleeper.sleeps[0]);
}

void test_429_waits_for_retry_after() { test_it_waits_as_long_as_the_broker_asks(429); }
void test_503_waits_for_retry_after() { test_it_waits_as_long_as_the_broker_asks(503); }

void test_429_without_retry_after_waits_the_default() {
  Board board;
  board.http.reply(429);
  board.http.reply(201);

  board.registrar().registerDevice();

  TEST_ASSERT_EQUAL(kDefaultRetryS, board.sleeper.sleeps[0]);
}

void test_409_registers_a_new_secret_straight_away() {
  Board board;
  board.store.values[kDeviceSecretKey] = "a renderer's";
  board.http.reply(409);
  board.http.reply(201);

  DisplayRegistrar registrar = board.registrar();
  registrar.registerDevice();

  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, registrar.secret());
  TEST_ASSERT_TRUE(board.sleeper.sleeps.empty());
  const SentRequest& retry = board.http.requests[1];
  TEST_ASSERT_EQUAL_STD_STRING(registerBody(kFirstToken), retry.body);
  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, retry.bearer);
  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, *retry.storedSecret);
  TEST_ASSERT_TRUE(board.log.has(LogLevel::Warning, "other role"));
}

void test_400_logs_the_brokers_reason_and_waits_the_default() {
  Board board;
  board.http.reply(400, "5", R"({"error": "role must be one of renderer, display"})");
  board.http.reply(201);

  board.registrar().registerDevice();

  TEST_ASSERT_TRUE(board.log.has(LogLevel::Error, "role must be one of renderer, display"));
  TEST_ASSERT_EQUAL(kDefaultRetryS, board.sleeper.sleeps[0]);
}

void test_an_unexpected_status_is_logged_and_waits_the_default() {
  Board board;
  board.http.reply(500, "5");
  board.http.reply(201);

  board.registrar().registerDevice();

  TEST_ASSERT_TRUE(board.log.has(LogLevel::Warning, std::string("Unexpected 500 from ") + kRegisterUrl));
  TEST_ASSERT_EQUAL(kDefaultRetryS, board.sleeper.sleeps[0]);
}

void test_an_unreachable_broker_is_retried_after_the_default() {
  Board board;
  board.http.fail("connection refused");
  board.http.fail("connection refused");
  board.http.reply(201);

  board.registrar().registerDevice();

  TEST_ASSERT_EQUAL(3, board.http.requests.size());
  TEST_ASSERT_EQUAL(2, board.sleeper.sleeps.size());
  TEST_ASSERT_EQUAL(kDefaultRetryS, board.sleeper.sleeps[0]);
  TEST_ASSERT_TRUE(board.log.has(LogLevel::Warning, "Couldn't register with the broker: connection refused"));
}

void test_retries_keep_the_same_secret() {
  Board board;
  board.http.fail("timed out");
  board.http.reply(503);
  board.http.reply(201);

  board.registrar().registerDevice();

  for (const SentRequest& sent : board.http.requests) {
    TEST_ASSERT_EQUAL_STD_STRING(registerBody(kFirstToken), sent.body);
  }
  TEST_ASSERT_EQUAL(24, board.random.next);
}

}  // namespace

void runDisplayRegistrarTests() {
  RUN_TEST(test_a_new_device_saves_its_secret_before_sending_it);
  RUN_TEST(test_it_posts_the_display_role_and_secret_with_the_secret_as_bearer);
  RUN_TEST(test_a_saved_secret_is_reused_and_registered_again);
  RUN_TEST(test_an_empty_saved_secret_is_replaced);
  RUN_TEST(test_trailing_slashes_are_dropped_from_the_broker_url);
  RUN_TEST(test_200_registers);
  RUN_TEST(test_201_registers);
  RUN_TEST(test_202_registers);
  RUN_TEST(test_429_waits_for_retry_after);
  RUN_TEST(test_503_waits_for_retry_after);
  RUN_TEST(test_429_without_retry_after_waits_the_default);
  RUN_TEST(test_409_registers_a_new_secret_straight_away);
  RUN_TEST(test_400_logs_the_brokers_reason_and_waits_the_default);
  RUN_TEST(test_an_unexpected_status_is_logged_and_waits_the_default);
  RUN_TEST(test_an_unreachable_broker_is_retried_after_the_default);
  RUN_TEST(test_retries_keep_the_same_secret);
}
