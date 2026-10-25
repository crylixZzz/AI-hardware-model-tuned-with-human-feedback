#include <stdint.h>
#include <stdbool.h>
#include <atomic>

#define RB_CAP 256u
#define RB_MASK (RB_CAP - 1u)

static uint8_t g_buf[RB_CAP];
static std::atomic<uint32_t> g_head;  // written by producer only
static std::atomic<uint32_t> g_tail;  // written by consumer only

void rb_init(void) {
    g_head.store(0, std::memory_order_relaxed);
    g_tail.store(0, std::memory_order_relaxed);
}

bool rb_push(uint8_t byte) {
    uint32_t head = g_head.load(std::memory_order_relaxed);
    uint32_t tail = g_tail.load(std::memory_order_acquire);
    if ((head - tail) >= RB_CAP) return false;
    g_buf[head & RB_MASK] = byte;
    g_head.store(head + 1, std::memory_order_release);
    return true;
}

bool rb_pop(uint8_t *out) {
    uint32_t tail = g_tail.load(std::memory_order_relaxed);
    uint32_t head = g_head.load(std::memory_order_acquire);
    if (head == tail) return false;
    *out = g_buf[tail & RB_MASK];
    g_tail.store(tail + 1, std::memory_order_release);
    return true;
}
