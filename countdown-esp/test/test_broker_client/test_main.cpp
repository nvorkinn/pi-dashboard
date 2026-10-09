#include <unity.h>

void setUp() {}
void tearDown() {}

void runTokenTests();
void runRetryTests();
void runDisplayRegistrarTests();
void runFrameClientTests();
void runLogBufferTests();

int main() {
  UNITY_BEGIN();
  runTokenTests();
  runRetryTests();
  runDisplayRegistrarTests();
  runFrameClientTests();
  runLogBufferTests();
  return UNITY_END();
}
