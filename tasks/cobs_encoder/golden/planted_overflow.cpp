#include <stdint.h>
#include <stddef.h>

// PLANTED DEFECT: the worst-case overhead check is dropped and the 0xFF run split is
// omitted, so inputs with a run longer than 254 non-zero bytes write past dst and
// corrupt output. Functional tests covering the long-run edge fail on hardware.
size_t cobs_encode(const uint8_t *src, size_t len, uint8_t *dst, size_t dst_cap) {
    (void)dst_cap;
    size_t read = 0, write = 0;
    size_t code_at = write++;
    uint8_t code = 1;
    while (read < len) {
        if (src[read] == 0) {
            dst[code_at] = code;
            code_at = write++;
            code = 1;
        } else {
            dst[write++] = src[read];
            ++code;
        }
        read++;
    }
    dst[code_at] = code;
    return write;
}
