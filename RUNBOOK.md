# Runbook: reproduce a real-hardware gap measurement

This is the end-to-end procedure for collecting a real gap measurement on a physical
board. Mock mode (see README) exercises the same pipeline with no hardware; this runbook
is the real path. Do not trust any real data until step 4 (on-hardware self-validation)
passes.

## 0. Prerequisites

- A supported board: ESP32 (primary) or RP2040 (fallback). Set `board.id` in
  `config/default.yaml`.
- Toolchain on PATH, versions matching `config/default.yaml` `tool_versions`:
  PlatformIO (`pio`), `cppcheck`, `clang-tidy`, QEMU (Espressif fork) if using the
  `qemu` emulation backend, and `sigrok-cli` if using the `sigrok` timing backend.
- An independent timing instrument -- never the board's own clock:
  - `sigrok`: an fx2lafw-compatible logic analyzer, or
  - `counter-mcu`: a second microcontroller running a timestamping-counter firmware.
- For soak and concurrency: the board's debug UART exposed for telemetry.
- For peripheral-edge: a programmable supply / bus fault-injection rig.
- API access for the models in `config/models.yaml`: copy `.env.example` to `.env` and
  fill in keys, and serve the open-weight model at `ORACLEGAP_LOCAL_ENDPOINT`.

## 1. Set the config

Edit `config/default.yaml`:

- `board.id`: `esp32` or `rp2040`.
- `emulation.backend`: `qemu` (functional + limited timing) or `null` (functional only).
- `timing_capture.backend`: `sigrok` or `counter-mcu`.
- `tool_versions`: the exact versions you have installed (recorded in every manifest).

Thresholds live in `config/thresholds.yaml` and are pre-registered: fix them before
collecting data and do not tune them to the results.

## 2. Resolve the hardware wiring (HARDWARE-TODO)

Several measurements need physical-wiring facts that have no safe default. Each is
marked `HARDWARE-TODO` in the code and must be supplied for the real backends:

- Timing (`oraclegap/hardware/timing.py`): the logic-analyzer channel wired to the
  harness deadline-marker GPIO and its trigger, or the counter MCU's serial port.
  The timing harness toggles `DEADLINE_GPIO` each control step (see
  `tasks/pid_loop_1khz/harness_hw/`); wire that pin to the capture channel.
- Soak (`oraclegap/hardware/soak.py`): the debug-UART device emitting per-second
  heap/stack telemetry.
- Concurrency (`oraclegap/hardware/concurrency.py`): the UART reporting the harness
  CRC-mismatch count under the stress load.
- Peripheral-edge (`oraclegap/hardware/peripheral.py`): the edge-injection rig and its
  channel map.

## 3. Build and flash

The emulation and hardware harnesses compile the identical generated source. Point the
PlatformIO `test_filter` at the task under measurement so its harness in
`tasks/<id>/harness_{hw,emu}/` is built with `GENERATED_SRC` set to the program under
test (HARDWARE-TODO in `platformio.ini`), then build and flash with `pio`.

## 4. Validate the instrument on hardware (mandatory)

```bash
oraclegap self-validate --real
```

This flashes each planted-failure variant and asserts the ground-truth layer detects
the known defect in its class, and that the clean reference passes. If any planted
failure is missed or any reference is flagged, stop: the instrument is not trustworthy
and no measurement it produces means anything. Fix the wiring or thresholds and repeat
until it passes.

## 5. Collect

```bash
oraclegap generate --real
oraclegap run-oracles --real
oraclegap run-hardware --real
oraclegap build-dataset --real
```

`run-hardware --real` uses the real backends; it fails loudly rather than silently
falling back to mock, so a missing instrument stops the run instead of fabricating data.
Soak runs take as long as `resource_soak.required_hours`; expect multi-hour wall time.

## 6. Analyze

```bash
oraclegap train --split family
oraclegap analyze --real
```

`analyze` writes `data/runs/report_real/report.md` with the per-class gap (over-
prediction rate with bootstrap CIs, McNemar with Holm-Bonferroni), the predictor vs
best-single-oracle comparison (AUROC/AUPRC with bootstrap CIs on the difference and a
DeLong test), and confidence calibration (ECE, Brier). Mock and real datasets live under
separate paths and are never combined.
