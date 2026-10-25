#include <stdint.h>
#include <stdbool.h>

#define RB_CAP 256u
#define RB_MASK (RB_CAP - 1u)

static uint8_t g_buf[RB_CAP];
static uint32_t g_head;
static uint32_t g_tail;
// PLANTED DEFECT: a shared element count is read-modified-written from both the ISR
// producer and the main consumer with no atomicity or ordering. Under contention the
// increment/decrement race loses updates, so bytes are dropped or double-counted.
// Single-threaded unit tests never contend, so they pass; only the hardware stress
// protocol surfaces the corruption.
static uint32_t g_count;

void rb_init(void) { g_head = 0; g_tail = 0; g_count = 0; }

bool rb_push(uint8_t byte) {
    if (g_count >= RB_CAP) return false;
    g_buf[g_head & RB_MASK] = byte;
    g_head++;
    g_count++;
    return true;
}

bool rb_pop(uint8_t *out) {
    if (g_count == 0) return false;
    *out = g_buf[g_tail & RB_MASK];
    g_tail++;
    g_count--;
    return true;
}
