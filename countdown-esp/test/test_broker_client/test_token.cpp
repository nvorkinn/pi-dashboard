#include <unity.h>

#include <string>

#include "fakes.h"
#include "token.h"

using namespace countdown;
using namespace countdown::testing;

namespace {

std::string encode(const std::string& text) {
  return base64UrlEncode(reinterpret_cast<const uint8_t*>(text.data()), text.size());
}

void test_base64url_matches_the_rfc_4648_vectors_without_padding() {
  TEST_ASSERT_EQUAL_STD_STRING("", encode(""));
  TEST_ASSERT_EQUAL_STD_STRING("Zg", encode("f"));
  TEST_ASSERT_EQUAL_STD_STRING("Zm8", encode("fo"));
  TEST_ASSERT_EQUAL_STD_STRING("Zm9v", encode("foo"));
  TEST_ASSERT_EQUAL_STD_STRING("Zm9vYg", encode("foob"));
  TEST_ASSERT_EQUAL_STD_STRING("Zm9vYmE", encode("fooba"));
  TEST_ASSERT_EQUAL_STD_STRING("Zm9vYmFy", encode("foobar"));
}

void test_base64url_uses_dash_and_underscore() {
  const uint8_t bytes[] = {0xFB, 0xFF, 0xBF};  // "+/+/" in standard base64
  TEST_ASSERT_EQUAL_STD_STRING("-_-_", base64UrlEncode(bytes, sizeof bytes));
}

void test_a_token_is_24_random_bytes_like_token_urlsafe() {
  CountingRandom random;

  const std::string token = tokenUrlsafe(random);

  TEST_ASSERT_EQUAL_STD_STRING(kFirstToken, token);
  TEST_ASSERT_EQUAL(32, token.size());
  TEST_ASSERT_EQUAL(24, random.next);
}

void test_each_token_takes_fresh_bytes() {
  CountingRandom random;

  tokenUrlsafe(random);

  TEST_ASSERT_EQUAL_STD_STRING(kSecondToken, tokenUrlsafe(random));
}

}  // namespace

void runTokenTests() {
  RUN_TEST(test_base64url_matches_the_rfc_4648_vectors_without_padding);
  RUN_TEST(test_base64url_uses_dash_and_underscore);
  RUN_TEST(test_a_token_is_24_random_bytes_like_token_urlsafe);
  RUN_TEST(test_each_token_takes_fresh_bytes);
}
