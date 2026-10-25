// Emulation harness. Same generated source and tests as harness_hw. These functional
// tests are single-threaded and therefore never contend; the race is only observable
// under the ISR/main stress protocol the hardware env enables (STRESS_PROTOCOL).
#include <unity.h>

#ifndef GENERATED_SRC
#define GENERATED_SRC "../golden/reference.cpp"
#endif
#include GENERATED_SRC

void rb_init(void);
bool rb_push(uint8_t);
bool rb_pop(uint8_t *);

void test_fifo_order(void) {
    rb_init();
    for (uint8_t i = 0; i < 100; i++) TEST_ASSERT_TRUE(rb_push(i));
    for (uint8_t i = 0; i < 100; i++) {
        uint8_t out;
        TEST_ASSERT_TRUE(rb_pop(&out));
        TEST_ASSERT_EQUAL_UINT8(i, out);
    }
}

void test_empty_and_full(void) {
    rb_init();
    uint8_t out;
    TEST_ASSERT_FALSE(rb_pop(&out));
    while (rb_push(0xAA)) {}
    TEST_ASSERT_FALSE(rb_push(0xAA));
}

void setup() {
    UNITY_BEGIN();
    RUN_TEST(test_fifo_order);
    RUN_TEST(test_empty_and_full);
    UNITY_END();
}

void loop() {}
