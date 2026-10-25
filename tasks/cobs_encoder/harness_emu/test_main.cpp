// Emulation harness. Compiles the identical generated source as harness_hw (the build
// sets GENERATED_SRC to the program under test); only the environment differs, so any
// emulation-vs-hardware divergence is a fidelity property, not a different program.
#include <unity.h>
#include <string.h>

#ifndef GENERATED_SRC
#define GENERATED_SRC "../golden/reference.cpp"
#endif
#include GENERATED_SRC

static bool has_zero(const uint8_t *p, size_t n) {
    for (size_t i = 0; i < n; i++) if (p[i] == 0) return true;
    return false;
}

void test_empty(void) {
    uint8_t dst[8];
    TEST_ASSERT_EQUAL(1, cobs_encode(nullptr, 0, dst, sizeof(dst)));
    TEST_ASSERT_EQUAL_UINT8(1, dst[0]);
}

void test_no_zero(void) {
    const uint8_t src[3] = {1, 2, 3};
    uint8_t dst[8];
    size_t n = cobs_encode(src, 3, dst, sizeof(dst));
    TEST_ASSERT_EQUAL(4, n);
    TEST_ASSERT_FALSE(has_zero(dst, n));
}

void test_all_zero(void) {
    const uint8_t src[3] = {0, 0, 0};
    uint8_t dst[8];
    size_t n = cobs_encode(src, 3, dst, sizeof(dst));
    TEST_ASSERT_EQUAL(4, n);
    TEST_ASSERT_FALSE(has_zero(dst, n));
}

void test_long_run(void) {
    uint8_t src[300];
    memset(src, 0xAB, sizeof(src));
    uint8_t dst[320];
    size_t n = cobs_encode(src, sizeof(src), dst, sizeof(dst));
    TEST_ASSERT_GREATER_THAN(sizeof(src), n);  // overhead byte inserted past 254
    TEST_ASSERT_FALSE(has_zero(dst, n));
}

void setup() {
    UNITY_BEGIN();
    RUN_TEST(test_empty);
    RUN_TEST(test_no_zero);
    RUN_TEST(test_all_zero);
    RUN_TEST(test_long_run);
    UNITY_END();
}

void loop() {}
