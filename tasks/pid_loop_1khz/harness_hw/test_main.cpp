// Hardware harness. Including the emulation harness keeps the board's tests and
// generated source byte-identical; the hardware env additionally defines
// DEADLINE_MARKER_LOOP to emit the external timing markers.
#define DEADLINE_MARKER_LOOP
#include "../harness_emu/test_main.cpp"
