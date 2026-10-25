# Limitations

Every place where a real-hardware result depends on manual setup or on backend fidelity,
so a reader knows exactly what the numbers do and do not rest on.

## Manual hardware setup (results are only as good as this)

- **Timing wiring.** The deadline-marker GPIO must be physically wired to the logic-
  analyzer channel (or counter MCU) named in the timing backend config. A wrong channel
  or a missing trigger silently yields empty or meaningless captures. There is no safe
  default; it is a `HARDWARE-TODO`.
- **Independent time base.** Timing ground truth is only valid if the capture instrument
  is independent of the device under test. Using the DUT's own clock would make a program
  that mis-measures its own timing look reliable. The framework refuses to read timing
  from the DUT, but it cannot verify your wiring is actually independent.
- **Soak and concurrency telemetry.** Both depend on the harness emitting the agreed
  heap/stack and CRC-mismatch lines on the debug UART, and on that UART being the one in
  config. A quiet or misparsed UART looks like a clean run.
- **Peripheral edge rig.** Electrical edges (brown-out thresholds, clock-stretch timing,
  bus contention) require the fault-injection rig. Without it there is no peripheral-edge
  measurement at all; it cannot be mocked onto real silicon.
- **Harness/source wiring in PlatformIO.** Mapping each task's harness to a build with
  the program under test (`GENERATED_SRC`, `test_filter`) is a manual per-run step.

## Emulation-backend fidelity

- The `qemu` backend currently reports functional results only; populating its
  `EmulationTiming` from QEMU's cycle counter is a `HARDWARE-TODO`. Until then, emulated
  timing is absent (not fabricated), and the sim-to-real timing gap cannot be computed
  from emulation alone.
- The `null` backend models no timing by construction. Any analysis of emulation timing
  fidelity requires a timing-capable backend.
- Emulation and hardware compile the identical generated source, but emulation cannot
  reproduce electrical or analog behavior; emulation-vs-hardware divergence conflates
  emulator-model error with genuinely unobservable-in-sim effects.

## Statistical and scope limits

- With one task per failure class, the family split holds out an entire class; the
  headline generalization number is to unseen failure *classes*, which is demanding and
  also means per-class estimates rest on a single task's programs. Adding more tasks per
  family strengthens both.
- Right-censored timing and soak runs are represented explicitly and excluded from the
  gap counts rather than imputed; a run cut short before its required window is labeled
  unknown, not a pass. Heavy censoring therefore shrinks usable sample size.
- Bootstrap CIs and DeLong tests assume the records are a representative sample of the
  task/model population; they do not correct for the specific task and model choices.

## Mock mode

- Mock mode exists to exercise the full pipeline, CI, and the self-validation gate with
  no hardware. Its numbers are synthetic by construction and are permanently labeled
  `source="mock"`; they are never evidence about real silicon and never mixed with real
  data. The mock is calibrated to reproduce the hypothesized qualitative result, which
  makes it a test of the framework, not a finding about any model.
