// Hardware harness. Identical generated source and tests as harness_emu; the hardware
// env drives the edge-injection rig against the real bus (PERIPHERAL_RIG) to exercise
// the electrical edges emulation cannot. HARDWARE-TODO: bind the rig channel map in
// hardware/peripheral.py.
#define PERIPHERAL_RIG
#include "../harness_emu/test_main.cpp"
