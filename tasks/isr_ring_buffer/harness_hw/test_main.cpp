// Hardware harness. Identical generated source and functional tests as harness_emu;
// the hardware env runs the concurrency stress protocol (ISR producer under a fixed
// load while main consumes) and reports CRC/sequence-mismatch events to the stressor.
// HARDWARE-TODO: bind the timer ISR that calls rb_push and the UART that reports the
// mismatch count; see hardware/concurrency.py.
#define STRESS_PROTOCOL
#include "../harness_emu/test_main.cpp"
