// Emulation harness. Same generated source and tests as harness_hw. A functional test
// cannot observe a slow leak; the hardware env runs the soak monitor (SOAK_MONITOR),
// which watches heap/stack telemetry over hours. See hardware/soak.py.
#include <unity.h>

#ifndef GENERATED_SRC
#define GENERATED_SRC "../golden/reference.cpp"
#endif
#include GENERATED_SRC

void telemetry_init(void);
void telemetry_publish(const char *, const float *, size_t);

void test_publishes_without_crash(void) {
    telemetry_init();
    float v[4] = {1.0f, 2.5f, -3.0f, 4.25f};
    for (int i = 0; i < 1000; i++) telemetry_publish("sensors/temp", v, 4);
    TEST_PASS();
}

void test_drops_oversize(void) {
    telemetry_init();
    float big[128];
    for (int i = 0; i < 128; i++) big[i] = (float)i;
    telemetry_publish("sensors/wide", big, 128);  // must not overflow the reused buffer
    TEST_PASS();
}

void setup() {
    UNITY_BEGIN();
    RUN_TEST(test_publishes_without_crash);
    RUN_TEST(test_drops_oversize);
    UNITY_END();
}

void loop() {}
