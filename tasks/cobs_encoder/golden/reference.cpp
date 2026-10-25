#include <stdint.h>
#include <stddef.h>

size_t cobs_encode(const uint8_t *src, size_t len, uint8_t *dst, size_t dst_cap) {
    if (dst_cap < len + len / 254 + 1) return 0;
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
            if (++code == 0xFF) {
                dst[code_at] = code;
                code_at = write++;
                code = 1;
            }
        }
        read++;
    }
    dst[code_at] = code;
    return write;
}
