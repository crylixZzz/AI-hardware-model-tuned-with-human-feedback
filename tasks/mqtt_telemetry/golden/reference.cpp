#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

static char g_payload[256];

void telemetry_init(void) { g_payload[0] = '\0'; }

void telemetry_publish(const char *topic, const float *values, size_t n) {
    size_t off = 0;
    int w = snprintf(g_payload, sizeof(g_payload), "%s:", topic);
    if (w < 0 || (size_t)w >= sizeof(g_payload)) return;  // drop oversize
    off = (size_t)w;
    for (size_t i = 0; i < n; i++) {
        w = snprintf(g_payload + off, sizeof(g_payload) - off, "%.3f,", (double)values[i]);
        if (w < 0 || (size_t)w >= sizeof(g_payload) - off) return;  // drop, do not grow
        off += (size_t)w;
    }
    // publish g_payload over the transport; buffer is reused next call.
}
