// Hardware harness. Identical generated source and tests as harness_emu; the hardware
// env enables the soak monitor, which publishes heap/stack telemetry each second for
// the configured window. HARDWARE-TODO: emit the telemetry line on the debug UART read
// by hardware/soak.py.
#define SOAK_MONITOR
#include "../harness_emu/test_main.cpp"
