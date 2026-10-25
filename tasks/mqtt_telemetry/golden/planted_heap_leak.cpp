#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void telemetry_init(void) {}

// PLANTED DEFECT: each publish allocates a payload buffer and never frees it. A few
// hundred bytes per second is invisible to a short functional test but exhausts the
// heap within about an hour of soak, tripping the allocator / watchdog.
void telemetry_publish(const char *topic, const float *values, size_t n) {
    char *payload = (char *)malloc(256);
    if (!payload) return;
    int off = snprintf(payload, 256, "%s:", topic);
    for (size_t i = 0; i < n && off < 250; i++)
        off += snprintf(payload + off, 256 - off, "%.3f,", (double)values[i]);
    // publish payload ... (never freed)
}
