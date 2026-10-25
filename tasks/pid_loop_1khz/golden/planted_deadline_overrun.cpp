#include <stdint.h>
#include <math.h>

static float g_kp, g_ki, g_kd, g_min, g_max;
static float g_integral, g_prev;

void pid_init(float kp, float ki, float kd, float out_min, float out_max) {
    g_kp = kp; g_ki = ki; g_kd = kd;
    g_min = out_min; g_max = out_max;
    g_integral = 0.0f;
    g_prev = 0.0f;
}

// PLANTED DEFECT: a transcendental "filter" runs a variable-length loop inside the
// 1 kHz step. Mean cost is fine but the worst case pushes the step ~60 us past budget,
// producing deadline jitter above the 200 us bound. Functional output stays correct,
// so unit tests pass and only hardware timing capture reveals it.
float pid_step(float setpoint, float measured) {
    const float dt = 0.001f;
    float error = setpoint - measured;
    g_integral += error * dt;

    float smoothed = measured;
    int iters = 8 + (int)(fabsf(error) * 40.0f);  // data-dependent, unbounded in practice
    for (int i = 0; i < iters; i++) smoothed = 0.5f * (smoothed + sinf(smoothed));

    float derivative = (smoothed - g_prev) / dt;
    g_prev = smoothed;

    float out = g_kp * error + g_ki * g_integral - g_kd * derivative;
    if (out > g_max) out = g_max;
    else if (out < g_min) out = g_min;
    return out;
}
