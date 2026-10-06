#include <unity.h>

#include <string>

#include "display_registrar.h"
#include "fakes.h"
#include "retry.h"
#include "frame_client.h"

using namespace countdown;
using namespace countdown::testing;

namespace {

constexpr char kFrameBody[] = R"({"role":"display"})";

// A FrameClient on a board whose secret is already saved, so the tests can tell
// registrations (POST) and frame polls (GET) apart by method.
struct Client {
  Board board;
  DisplayRegistrar registrar;
  FrameClient client;

  Client() : registrar(withSecret(board)), client(registrar, board.http, board.sleeper, board.log) {}

  static DisplayRegistrar withSecret(Board& board) {
    board.store.values[kDeviceSecretKey] = "shh";
    return board.registrar();
  }

  int count(const std::string& method) const {
    int n = 0;
    for (const SentRequest& sent : board.http.requests) {
      n += sent.method == method;
    }
    return n;
  }
};

void test_the_first_tick_registers_then_polls_the_frame() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(202, "5");

  c.client.tick();

  TEST_ASSERT_EQUAL(2, c.board.http.requests.size());
  TEST_ASSERT_EQUAL_STD_STRING("POST", c.board.http.requests[0].method);
  const SentRequest& poll = c.board.http.requests[1];
  TEST_ASSERT_EQUAL_STD_STRING("GET", poll.method);
  TEST_ASSERT_EQUAL_STD_STRING(kFrameUrl, poll.url);
  TEST_ASSERT_EQUAL_STD_STRING(kFrameBody, poll.body);
  TEST_ASSERT_EQUAL_STD_STRING("shh", poll.bearer);
}

void test_later_ticks_only_poll() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(202);
  c.board.http.reply(304);
  c.board.http.reply(404);

  c.client.tick();
  c.client.tick();
  c.client.tick();

  TEST_ASSERT_EQUAL(1, c.count("POST"));
  TEST_ASSERT_EQUAL(3, c.count("GET"));
}

void test_a_frame_is_logged_with_its_size() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(200, "30", std::string(48000, '\xFF'));

  c.client.tick();

  TEST_ASSERT_TRUE(c.board.log.has(LogLevel::Info, "Got a frame (48000 bytes)"));
  TEST_ASSERT_EQUAL(30, c.board.sleeper.sleeps.back());
}

void test_nothing_to_draw_is_quiet_and_waits_as_asked(int status) {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(status, "12");

  c.client.tick();

  for (const auto& [level, message] : c.board.log.lines) {
    TEST_ASSERT_TRUE_MESSAGE(level == LogLevel::Info && message == "Registered with the broker", message.c_str());
  }
  TEST_ASSERT_EQUAL(1, c.board.sleeper.sleeps.size());
  TEST_ASSERT_EQUAL(12, c.board.sleeper.sleeps[0]);
}

// Not matched with a renderer yet
void test_202_is_quiet() { test_nothing_to_draw_is_quiet_and_waits_as_asked(202); }
// Nothing has changed since last poll
void test_304_is_quiet() { test_nothing_to_draw_is_quiet_and_waits_as_asked(304); }
// Matched, but nothing rendered yet
void test_404_is_quiet() { test_nothing_to_draw_is_quiet_and_waits_as_asked(404); }

void test_a_poll_without_retry_after_waits_the_default() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(304);

  c.client.tick();

  TEST_ASSERT_EQUAL(kDefaultRetryS, c.board.sleeper.sleeps[0]);
}

void test_401_registers_again_with_the_same_secret_on_the_next_tick() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(401, "30");
  c.board.http.reply(201);
  c.board.http.reply(202);

  c.client.tick();
  TEST_ASSERT_TRUE(c.board.sleeper.sleeps.empty());  // straight back to registering
  c.client.tick();

  TEST_ASSERT_EQUAL(2, c.count("POST"));
  TEST_ASSERT_EQUAL_STD_STRING("POST", c.board.http.requests[2].method);
  TEST_ASSERT_EQUAL_STD_STRING(R"({"role":"display","secret":"shh"})", c.board.http.requests[2].body);
  TEST_ASSERT_EQUAL_STD_STRING("GET", c.board.http.requests[3].method);
  TEST_ASSERT_EQUAL_STD_STRING("shh", c.board.http.requests[3].bearer);
}

void test_an_unexpected_status_is_logged_and_waits_as_asked() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(500, "9");

  c.client.tick();

  TEST_ASSERT_TRUE(c.board.log.has(LogLevel::Warning, std::string("Unexpected 500 from ") + kFrameUrl));
  TEST_ASSERT_EQUAL(9, c.board.sleeper.sleeps[0]);
  TEST_ASSERT_EQUAL(1, c.count("POST"));
}

void test_an_unreachable_broker_is_polled_again_after_the_default() {
  Client c;
  c.board.http.reply(201);
  c.board.http.fail("connection reset");
  c.board.http.reply(304);

  c.client.tick();
  c.client.tick();

  TEST_ASSERT_TRUE(c.board.log.has(LogLevel::Warning, "Couldn't fetch the frame: connection reset"));
  TEST_ASSERT_EQUAL(kDefaultRetryS, c.board.sleeper.sleeps[0]);
  TEST_ASSERT_EQUAL(1, c.count("POST"));
  TEST_ASSERT_EQUAL(2, c.count("GET"));
}

void test_polls_carry_the_new_secret_after_a_409() {
  Board board;
  board.store.values[kDeviceSecretKey] = "a renderer's";
  DisplayRegistrar registrar = board.registrar();
  FrameClient client(registrar, board.http, board.sleeper, board.log);
  board.http.reply(409);
  board.http.reply(201);
  board.http.reply(202);

  client.tick();

  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, board.http.requests[2].bearer);
}

}  // namespace

void runFrameClientTests() {
  RUN_TEST(test_the_first_tick_registers_then_polls_the_frame);
  RUN_TEST(test_later_ticks_only_poll);
  RUN_TEST(test_a_frame_is_logged_with_its_size);
  RUN_TEST(test_202_is_quiet);
  RUN_TEST(test_304_is_quiet);
  RUN_TEST(test_404_is_quiet);
  RUN_TEST(test_a_poll_without_retry_after_waits_the_default);
  RUN_TEST(test_401_registers_again_with_the_same_secret_on_the_next_tick);
  RUN_TEST(test_an_unexpected_status_is_logged_and_waits_as_asked);
  RUN_TEST(test_an_unreachable_broker_is_polled_again_after_the_default);
  RUN_TEST(test_polls_carry_the_new_secret_after_a_409);
}
