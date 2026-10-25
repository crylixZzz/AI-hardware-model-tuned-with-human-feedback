#include <stdint.h>

static float g_kp, g_ki, g_kd, g_min, g_max;
static float g_integral, g_prev;

void pid_init(float kp, float ki, float kd, float out_min, float out_max) {
    g_kp = kp; g_ki = ki; g_kd = kd;
    g_min = out_min; g_max = out_max;
    g_integral = 0.0f;
    g_prev = 0.0f;
}

float pid_step(float setpoint, float measured) {
    const float dt = 0.001f;
    float error = setpoint - measured;
    g_integral += error * dt;
    // Clamp the integrator to the output range to prevent windup.
    float i_term = g_ki * g_integral;
    if (i_term > g_max) g_integral = g_max / g_ki;
    else if (i_term < g_min) g_integral = g_min / g_ki;

    float derivative = (measured - g_prev) / dt;
    g_prev = measured;

    float out = g_kp * error + g_ki * g_integral - g_kd * derivative;
    if (out > g_max) out = g_max;
    else if (out < g_min) out = g_min;
    return out;
}
