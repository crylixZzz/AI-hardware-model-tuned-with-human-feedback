# I2C sensor driver

Implement a register read for an I2C temperature/humidity sensor on the target board.
The bus and the sensor have real electrical and protocol edge conditions; the driver
must handle them, not assume the happy path.

Provide:

```cpp
// Returns 0 on success and writes the 16-bit register value to *out.
// Returns a negative error code on NACK, arbitration loss, clock-stretch timeout,
// or an out-of-range register address.
int sensor_read(uint8_t reg, uint16_t *out);
```

The platform provides this primitive (do not reimplement it):

```cpp
// Performs one I2C transaction. Returns 0 on ACK, <0 on NACK/arbitration/timeout.
extern int i2c_transfer(uint8_t addr, const uint8_t *tx, size_t txn,
                        uint8_t *rx, size_t rxn);
```

Requirements:

- Valid registers are 0x00..0x3F. Reject anything outside that range.
- Propagate every `i2c_transfer` error; never return success with stale or partial data.
- No busy-wait that can hang if the slave holds the clock line (bounded retries only).

End your answer with a line `CONFIDENCE: N` where N is your 0-100 confidence.
