#include <unity.h>

void setUp() {}
void tearDown() {}

void runEpd7in5V2Tests();
void runEpdDisplayTests();

int main() {
  UNITY_BEGIN();
  runEpd7in5V2Tests();
  runEpdDisplayTests();
  return UNITY_END();
}
