#include <unity.h>

#include "captive_probe.h"

using countdown::isAppleProbeHost;

namespace {

void test_apple_com_itself() { TEST_ASSERT_TRUE(isAppleProbeHost("apple.com")); }

void test_subdomains() {
  TEST_ASSERT_TRUE(isAppleProbeHost("captive.apple.com"));
  TEST_ASSERT_TRUE(isAppleProbeHost("gsp1.apple.com"));
  TEST_ASSERT_TRUE(isAppleProbeHost("a.b.apple.com"));
}

void test_upper_case() { TEST_ASSERT_TRUE(isAppleProbeHost("Captive.Apple.COM")); }

void test_port_is_ignored() {
  TEST_ASSERT_TRUE(isAppleProbeHost("captive.apple.com:80"));
  TEST_ASSERT_TRUE(isAppleProbeHost("apple.com:8080"));
}

void test_look_alikes() {
  TEST_ASSERT_FALSE(isAppleProbeHost("notapple.com"));
  TEST_ASSERT_FALSE(isAppleProbeHost("apple.com.evil.example"));
  TEST_ASSERT_FALSE(isAppleProbeHost("apple.company"));
  TEST_ASSERT_FALSE(isAppleProbeHost("evil.example/apple.com"));
}

void test_board_and_empty() {
  TEST_ASSERT_FALSE(isAppleProbeHost("192.168.4.1"));
  TEST_ASSERT_FALSE(isAppleProbeHost("example.com"));
  TEST_ASSERT_FALSE(isAppleProbeHost(""));
  TEST_ASSERT_FALSE(isAppleProbeHost(":80"));
  TEST_ASSERT_FALSE(isAppleProbeHost(".apple.com"));
}

}  // namespace

void runCaptiveProbeTests() {
  RUN_TEST(test_apple_com_itself);
  RUN_TEST(test_subdomains);
  RUN_TEST(test_upper_case);
  RUN_TEST(test_port_is_ignored);
  RUN_TEST(test_look_alikes);
  RUN_TEST(test_board_and_empty);
}
