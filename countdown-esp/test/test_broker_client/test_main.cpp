#include <unity.h>

void setUp() {}
void tearDown() {}

void runTokenTests();
void runRetryTests();
void runDisplayRegistrarTests();
void runFrameClientTests();

int main() {
  UNITY_BEGIN();
  runTokenTests();
  runRetryTests();
  runDisplayRegistrarTests();
  runFrameClientTests();
  return UNITY_END();
}
