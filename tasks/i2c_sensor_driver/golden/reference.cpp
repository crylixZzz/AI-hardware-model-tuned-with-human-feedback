#include <stdint.h>
#include <stddef.h>

extern int i2c_transfer(uint8_t addr, const uint8_t *tx, size_t txn, uint8_t *rx, size_t rxn);

#define SENSOR_ADDR 0x44
#define REG_MAX 0x3F
#define MAX_RETRY 3

int sensor_read(uint8_t reg, uint16_t *out) {
    if (reg > REG_MAX) return -1;

    uint8_t rx[2];
    int rc = -1;
    for (int attempt = 0; attempt < MAX_RETRY; attempt++) {
        rc = i2c_transfer(SENSOR_ADDR, &reg, 1, rx, 2);
        if (rc == 0) break;  // bounded retry; never spins forever on a held clock
    }
    if (rc != 0) return rc;  // propagate NACK / arbitration / timeout
    *out = (uint16_t)((rx[0] << 8) | rx[1]);
    return 0;
}
