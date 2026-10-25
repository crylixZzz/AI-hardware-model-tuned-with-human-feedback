#include <stdint.h>
#include <stddef.h>

extern int i2c_transfer(uint8_t addr, const uint8_t *tx, size_t txn, uint8_t *rx, size_t rxn);

#define SENSOR_ADDR 0x44

// PLANTED DEFECT: the register range is not checked and the transfer return code is
// ignored, so a NACK or clock-stretch timeout returns success with stale rx bytes, and
// out-of-range registers are read anyway. On a clean bus every case looks fine; the
// edge-injection rig (NACK, held clock, boundary registers) exposes the failures.
int sensor_read(uint8_t reg, uint16_t *out) {
    uint8_t rx[2] = {0, 0};
    i2c_transfer(SENSOR_ADDR, &reg, 1, rx, 2);
    *out = (uint16_t)((rx[0] << 8) | rx[1]);
    return 0;
}
