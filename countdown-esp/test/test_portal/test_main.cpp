#include <unity.h>

void setUp() {}
void tearDown() {}

void runCaptiveProbeTests();

int main() {
  UNITY_BEGIN();
  runCaptiveProbeTests();
  return UNITY_END();
}
