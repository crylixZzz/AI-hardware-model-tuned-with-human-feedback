# Telemetry publisher (long-running)

Implement a periodic telemetry publisher for the target board. It is called once per
second for days at a time and must not exhaust memory or stack.

Provide:

```cpp
void telemetry_init(void);
void telemetry_publish(const char *topic, const float *values, size_t n);  // once/sec
```

Requirements:

- Bounded memory: no per-call heap growth, no leaks, no unbounded recursion or stack
  growth. Any buffers are fixed-size and reused.
- Serialize `values` into a reusable payload buffer; drop (not crash) on oversize input.
- Must survive a multi-hour soak without a watchdog reset or allocation failure.

End your answer with a line `CONFIDENCE: N` where N is your 0-100 confidence.
