// Emulation harness. Same generated source and tests as harness_hw. Functional checks
// run under emulation; the deadline-marker loop below is what the external timing
// instrument observes on real hardware (the DUT never times itself -- see LIMITATIONS).
#include <unity.h>
#include <math.h>

#ifndef GENERATED_SRC
#define GENERATED_SRC "../golden/reference.cpp"
#endif
#include GENERATED_SRC

void pid_init(float, float, float, float, float);
float pid_step(float, float);

void test_drives_toward_setpoint(void) {
    pid_init(2.0f, 0.5f, 0.1f, -100.0f, 100.0f);
    float measured = 0.0f;
    for (int i = 0; i < 200; i++) {
        float u = pid_step(10.0f, measured);
        measured += 0.02f * u;  // toy plant
    }
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 10.0f, measured);
}

void test_output_clamped(void) {
    pid_init(1000.0f, 0.0f, 0.0f, -5.0f, 5.0f);
    float u = pid_step(1.0e6f, 0.0f);
    TEST_ASSERT_TRUE(u <= 5.0f && u >= -5.0f);
}

void setup() {
    UNITY_BEGIN();
    RUN_TEST(test_drives_toward_setpoint);
    RUN_TEST(test_output_clamped);
    UNITY_END();
}

void loop() {}

#ifdef DEADLINE_MARKER_LOOP
// Driven on hardware by the 1 kHz timer ISR; toggles the marker GPIO on each step so
// the logic analyzer / counter MCU can time deadline intervals externally.
// HARDWARE-TODO: set DEADLINE_GPIO to the pin wired to the capture channel.
#ifndef DEADLINE_GPIO
#define DEADLINE_GPIO 4
#endif
#include <Arduino.h>
void control_tick(float setpoint, float measured) {
    digitalWrite(DEADLINE_GPIO, HIGH);
    (void)pid_step(setpoint, measured);
    digitalWrite(DEADLINE_GPIO, LOW);
}
#endif
