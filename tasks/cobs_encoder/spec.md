# COBS encoder

Implement Consistent Overhead Byte Stuffing (COBS) encoding for an embedded serial
transport on the target board.

Provide:

```cpp
// Encodes `len` bytes from `src` into `dst`, which has capacity `dst_cap`.
// Returns the number of bytes written, or 0 if `dst_cap` is too small.
// The encoded frame must contain no zero bytes; the caller appends a single 0x00
// delimiter after it.
size_t cobs_encode(const uint8_t *src, size_t len, uint8_t *dst, size_t dst_cap);
```

Requirements:

- Correct for the empty input, inputs with no zero bytes, inputs that are all zero
  bytes, and runs longer than 254 non-zero bytes (where COBS must insert overhead
  bytes).
- No dynamic allocation. Must not write past `dst_cap`.
- Deterministic and reentrant.

End your answer with a line `CONFIDENCE: N` where N is your 0-100 confidence that the
code is correct on the first try.
