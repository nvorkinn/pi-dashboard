#include <unity.h>

#include <string>

#include "display_registrar.h"
#include "fakes.h"
#include "retry.h"
#include "frame_client.h"

using namespace countdown;
using namespace countdown::testing;

namespace {

// A FrameClient on a board whose secret is already saved, so its first registration
// succeeds without minting a new one.
struct Client {
  Board board;
  DisplayRegistrar registrar;
  FrameClient client;

  Client() : registrar(withSecret(board)), client(registrar, board.http, board.display, board.sleeper, board.logs, board.metrics) {}

  static DisplayRegistrar withSecret(Board& board) {
    board.store.values[kDeviceSecretKey] = "shh";
    return board.registrar();
  }

  int count(const std::string& url) const {
    int n = 0;
    for (const SentRequest& sent : board.http.requests) {
      n += sent.url == url;
    }
    return n;
  }

  const std::string& lastBody() const { return board.http.requests.back().body; }
};

void test_the_first_tick_registers_then_polls_the_frame() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(202, "5");

  c.client.tick();

  TEST_ASSERT_EQUAL(2, c.board.http.requests.size());
  TEST_ASSERT_EQUAL_STD_STRING(kRegisterUrl, c.board.http.requests[0].url);
  const SentRequest& poll = c.board.http.requests[1];
  TEST_ASSERT_EQUAL_STD_STRING("POST", poll.method);
  TEST_ASSERT_EQUAL_STD_STRING(kFrameUrl, poll.url);
  TEST_ASSERT_EQUAL_STD_STRING(
      R"({"role":"display","metrics":"esp32,device_id={device_id} logs_dropped=0i",)"
      R"("logs":[{"uptime_ms":0,"level":"INFO","message":"Registered with the broker"}]})",
      poll.body);
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

  TEST_ASSERT_EQUAL(1, c.count(kRegisterUrl));
  TEST_ASSERT_EQUAL(3, c.count(kFrameUrl));
}

void test_a_frame_is_logged_with_its_size() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(200, "30", std::string(48000, '\xFF'));

  c.client.tick();

  TEST_ASSERT_TRUE(c.board.log.has(LogLevel::Info, "Got a frame (48000 bytes)"));
  TEST_ASSERT_EQUAL(30, c.board.sleeper.sleeps.back());
}

void test_a_frame_is_drawn() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(200, "30", "\x01\x02\x03");

  c.client.tick();

  TEST_ASSERT_EQUAL(1, c.board.display.shown.size());
  const std::vector<uint8_t> expected = {0x01, 0x02, 0x03};
  TEST_ASSERT_TRUE(c.board.display.shown[0] == expected);
  TEST_ASSERT_FALSE(c.board.log.has(LogLevel::Error, "Couldn't draw"));
}

void test_a_frame_that_cant_be_drawn_is_logged_and_polling_carries_on() {
  Client c;
  c.board.display.succeeds = false;
  c.board.http.reply(201);
  c.board.http.reply(200, "30", "frame");
  c.board.http.reply(304);

  c.client.tick();
  c.client.tick();

  TEST_ASSERT_TRUE(c.board.log.has(LogLevel::Error, "Couldn't draw the frame"));
  TEST_ASSERT_EQUAL(30, c.board.sleeper.sleeps[0]);
  TEST_ASSERT_EQUAL(1, c.count(kRegisterUrl));
  TEST_ASSERT_EQUAL(2, c.count(kFrameUrl));
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
  TEST_ASSERT_TRUE(c.board.display.shown.empty());
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

  TEST_ASSERT_EQUAL(2, c.count(kRegisterUrl));
  TEST_ASSERT_EQUAL_STD_STRING(kRegisterUrl, c.board.http.requests[2].url);
  TEST_ASSERT_EQUAL_STD_STRING(R"({"role":"display","secret":"shh"})", c.board.http.requests[2].body);
  TEST_ASSERT_EQUAL_STD_STRING(kFrameUrl, c.board.http.requests[3].url);
  TEST_ASSERT_EQUAL_STD_STRING("shh", c.board.http.requests[3].bearer);
}

void test_an_unexpected_status_is_logged_and_waits_as_asked() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(500, "9");

  c.client.tick();

  TEST_ASSERT_TRUE(c.board.log.has(LogLevel::Warning, std::string("Unexpected 500 from ") + kFrameUrl));
  TEST_ASSERT_EQUAL(9, c.board.sleeper.sleeps[0]);
  TEST_ASSERT_EQUAL(1, c.count(kRegisterUrl));
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
  TEST_ASSERT_EQUAL(1, c.count(kRegisterUrl));
  TEST_ASSERT_EQUAL(2, c.count(kFrameUrl));
}

void test_polls_carry_the_new_secret_after_a_409() {
  Board board;
  board.store.values[kDeviceSecretKey] = "a renderer's";
  DisplayRegistrar registrar = board.registrar();
  FrameClient client(registrar, board.http, board.display, board.sleeper, board.logs, board.metrics);
  board.http.reply(409);
  board.http.reply(201);
  board.http.reply(202);

  client.tick();

  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, board.http.requests[2].bearer);
}

void test_polls_carry_the_metrics_and_how_many_lines_were_dropped() {
  Client c;
  c.board.metrics.readings = {{"free_heap", 182344}, {"wifi_rssi", -61}};
  c.board.http.reply(201);
  c.board.http.reply(202);

  c.client.tick();

  TEST_ASSERT_NOT_EQUAL(std::string::npos,
                        c.lastBody().find(
                            R"("metrics":"esp32,device_id={device_id} free_heap=182344i,wifi_rssi=-61i,logs_dropped=0i")"));
}

void test_polls_carry_the_logs_with_their_uptime_level_and_escaped_message() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(202);
  c.board.clock.now = 1234;
  c.board.logs.warning("say \"hi\"\nback\\slash");

  c.client.tick();

  TEST_ASSERT_NOT_EQUAL(
      std::string::npos,
      c.lastBody().find(R"({"uptime_ms":1234,"level":"WARNING","message":"say \"hi\"\nback\\slash"})"));
}

void test_logs_the_broker_answered_are_not_sent_again() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(202);
  c.board.http.reply(304);

  c.client.tick();
  c.client.tick();

  TEST_ASSERT_NOT_EQUAL(std::string::npos, c.board.http.requests[1].body.find("Registered with the broker"));
  TEST_ASSERT_NOT_EQUAL(std::string::npos, c.lastBody().find(R"("logs":[]})"));
}

void test_lines_logged_after_the_answer_go_with_the_next_poll() {
  Client c;
  c.board.http.reply(201);
  c.board.http.reply(200, "30", "frame");
  c.board.http.reply(304);

  c.client.tick();
  c.client.tick();

  TEST_ASSERT_EQUAL(std::string::npos, c.lastBody().find("Registered with the broker"));
  TEST_ASSERT_NOT_EQUAL(std::string::npos, c.lastBody().find("Got a frame (5 bytes)"));
}

void test_logs_are_kept_until_the_broker_answers(void (*notAnswered)(FakeHttp&)) {
  Client c;
  c.board.http.reply(201);
  notAnswered(c.board.http);
  c.board.http.reply(202);

  c.client.tick();
  c.client.tick();

  TEST_ASSERT_EQUAL_STD_STRING(kFrameUrl, c.board.http.requests.back().url);
  TEST_ASSERT_TRUE(c.board.http.responses.empty());
  TEST_ASSERT_NOT_EQUAL(std::string::npos, c.lastBody().find("Registered with the broker"));
}

void test_logs_are_kept_when_the_broker_is_unreachable() {
  test_logs_are_kept_until_the_broker_answers([](FakeHttp& http) { http.fail("connection reset"); });
}
void test_logs_are_kept_after_a_500() {
  test_logs_are_kept_until_the_broker_answers([](FakeHttp& http) { http.reply(500); });
}
void test_logs_are_kept_after_a_401() {
  test_logs_are_kept_until_the_broker_answers([](FakeHttp& http) {
    http.reply(401);
    http.reply(201);  // Registering again
  });
}

}  // namespace

void runFrameClientTests() {
  RUN_TEST(test_the_first_tick_registers_then_polls_the_frame);
  RUN_TEST(test_later_ticks_only_poll);
  RUN_TEST(test_a_frame_is_logged_with_its_size);
  RUN_TEST(test_a_frame_is_drawn);
  RUN_TEST(test_a_frame_that_cant_be_drawn_is_logged_and_polling_carries_on);
  RUN_TEST(test_202_is_quiet);
  RUN_TEST(test_304_is_quiet);
  RUN_TEST(test_404_is_quiet);
  RUN_TEST(test_a_poll_without_retry_after_waits_the_default);
  RUN_TEST(test_401_registers_again_with_the_same_secret_on_the_next_tick);
  RUN_TEST(test_an_unexpected_status_is_logged_and_waits_as_asked);
  RUN_TEST(test_an_unreachable_broker_is_polled_again_after_the_default);
  RUN_TEST(test_polls_carry_the_new_secret_after_a_409);
  RUN_TEST(test_polls_carry_the_metrics_and_how_many_lines_were_dropped);
  RUN_TEST(test_polls_carry_the_logs_with_their_uptime_level_and_escaped_message);
  RUN_TEST(test_logs_the_broker_answered_are_not_sent_again);
  RUN_TEST(test_lines_logged_after_the_answer_go_with_the_next_poll);
  RUN_TEST(test_logs_are_kept_when_the_broker_is_unreachable);
  RUN_TEST(test_logs_are_kept_after_a_500);
  RUN_TEST(test_logs_are_kept_after_a_401);
}
