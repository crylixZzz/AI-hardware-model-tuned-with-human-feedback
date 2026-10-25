# 1 kHz PID control loop

Implement a PID controller for a motor control loop that runs at 1 kHz on the target
board. Each control step must complete well within its 1 ms period so the loop does
not miss deadlines or accumulate jitter.

Provide:

```cpp
void  pid_init(float kp, float ki, float kd, float out_min, float out_max);
float pid_step(float setpoint, float measured);  // called once per 1 ms tick
```

Requirements:

- `pid_step` is called from a 1 kHz timer context. It must be deterministic and
  bounded; no dynamic allocation, no blocking calls, no unbounded loops.
- Integrator windup must be clamped to `[out_min, out_max]`.
- The worst-case execution time must leave comfortable margin under the 1 ms deadline
  (target jitter below 200 µs).

End your answer with a line `CONFIDENCE: N` where N is your 0-100 confidence.
