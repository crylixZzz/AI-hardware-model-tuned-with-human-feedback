# ISR-safe ring buffer

Implement a single-producer/single-consumer byte ring buffer. The producer runs in an
interrupt service routine; the consumer runs in the main loop. No locks, no disabling
interrupts.

Provide:

```cpp
void   rb_init(void);
bool   rb_push(uint8_t byte);  // producer (ISR context); false if full
bool   rb_pop(uint8_t *out);   // consumer (main context); false if empty
```

Requirements:

- Correct under concurrent producer/consumer access with no lost or duplicated bytes
  and no reads of partially written state. Indices shared across contexts must be
  declared and ordered so the compiler and CPU cannot reorder the critical writes.
- Fixed capacity, power of two, no dynamic allocation.

End your answer with a line `CONFIDENCE: N` where N is your 0-100 confidence.
