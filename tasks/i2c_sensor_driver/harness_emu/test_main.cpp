// Emulation harness. Same generated source and tests as harness_hw. The fake
// i2c_transfer below reproduces protocol edges (NACK, bad register); the genuinely
// electrical edges (clock-stretch timing, brown-out) are only exercised on hardware
// by the edge-injection rig (PERIPHERAL_RIG). See hardware/peripheral.py.
#include <unity.h>

#ifndef GENERATED_SRC
#define GENERATED_SRC "../golden/reference.cpp"
#endif

static int g_transfer_rc = 0;
static uint8_t g_rx0 = 0x12, g_rx1 = 0x34;

int i2c_transfer(uint8_t addr, const uint8_t *tx, size_t txn, uint8_t *rx, size_t rxn) {
    (void)addr; (void)tx; (void)txn;
    if (g_transfer_rc == 0 && rxn >= 2) { rx[0] = g_rx0; rx[1] = g_rx1; }
    return g_transfer_rc;
}

#include GENERATED_SRC

int sensor_read(uint8_t reg, uint16_t *out);

void test_happy_path(void) {
    g_transfer_rc = 0;
    uint16_t v = 0;
    TEST_ASSERT_EQUAL(0, sensor_read(0x10, &v));
    TEST_ASSERT_EQUAL_HEX16(0x1234, v);
}

void test_nack_propagates(void) {
    g_transfer_rc = -2;
    uint16_t v = 0;
    TEST_ASSERT_LESS_THAN(0, sensor_read(0x10, &v));
}

void test_register_out_of_range(void) {
    g_transfer_rc = 0;
    uint16_t v = 0;
    TEST_ASSERT_LESS_THAN(0, sensor_read(0x40, &v));
}

void setup() {
    UNITY_BEGIN();
    RUN_TEST(test_happy_path);
    RUN_TEST(test_nack_propagates);
    RUN_TEST(test_register_out_of_range);
    UNITY_END();
}

void loop() {}
