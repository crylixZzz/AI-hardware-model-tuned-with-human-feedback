# Oracle Gap

A measurement framework for the gap between cheap code oracles and real-hardware
reliability of AI-generated embedded code.

Cheap oracles for embedded code -- unit tests (pass@k), static analysis, emulation, and
the model's own confidence -- are structurally blind to failure classes that only appear
on real silicon: timing/deadline misses, interrupt/concurrency races, slow resource
exhaustion, and peripheral/electrical edges. This framework calls external LLMs to
generate embedded programs, runs those oracles, measures real-hardware ground truth per
failure class, and quantifies how often the oracles mispredict.

It is **not** a language model. Nothing here is trained or served as an LLM; the only
learned model is a small supervised predictor of hardware reliability.

It produces two things:

1. **The gap dataset** -- for each generated program, every cheap-oracle prediction and
   the real-hardware outcome per failure class, so their divergence is directly
   computable.
2. **The predictor** -- a supervised model that predicts real-hardware failure from
   pre-deployment features and is evaluated honestly against the best single cheap
   oracle, split by task family (not randomly).

## The ground-truth layer is the instrument

The whole point is to measure oracle error against hardware truth, so a silent bug in
the ground-truth layer would corrupt every result. That layer therefore proves itself:
each task ships a clean reference and planted-failure variants with known defects, and
`self-validate` asserts the instrument detects each planted failure in its class and
passes the clean reference. It runs in mock mode in CI and is re-runnable on hardware
before any real data collection. Every record carries a `source` field (`real` | `mock`);
the store refuses to mix them, and measurements come only from the path the source names.

## Install

Requires Python 3.11+.

```bash
pip install -e .
```

## Mock-mode quickstart (no hardware)

Every backend has a seeded mock implementation, so the full pipeline runs with no board
and no API keys:

```bash
oraclegap self-validate          # prove the instrument catches planted failures
oraclegap generate               # sample code from the configured models
oraclegap run-oracles            # cheap oracles over the samples
oraclegap run-hardware           # ground-truth layer (mock captures)
oraclegap build-dataset          # assemble validated records -> Parquet
oraclegap train --split family   # fit the predictor, family-split headline
oraclegap analyze                # gap, calibration, statistics -> tables + figures
```

`analyze` writes `data/runs/report_<source>/report.md` (plus figures when matplotlib is
installed: `pip install -e '.[viz]'`). Every command also writes a run manifest under
`data/runs/` recording the config hash, tool and model versions, git commit, and UTC
timestamp.

In mock mode the dataset reproduces the hypothesized result: the oracle over-predicts
reliability on the non-functional classes (timing, concurrency, resource-soak,
peripheral-edge) but not on the functional class, the divergence is significant by
McNemar after Holm-Bonferroni, model confidence is badly over-confident against the
hardware outcome, and the learned predictor beats the best single cheap oracle on the
family split.

## Real hardware

See [RUNBOOK.md](RUNBOOK.md) for the end-to-end procedure on a physical board, including
the mandatory on-hardware self-validation before trusting any data.
[LIMITATIONS.md](LIMITATIONS.md) lists every place results depend on manual setup or on
emulation-backend fidelity.

## Layout

- `oraclegap/` -- the Python package (schemas, generation, oracles, hardware, ground
  truth, predictor, analysis, validation, CLI).
- `tasks/` -- one task per failure class, each with a spec, matched emulation/hardware
  harnesses, and golden reference plus planted-failure variants.
- `config/` -- run config, pinned model registry, and pre-registered analysis thresholds.
- `tests/` -- mock-mode end-to-end and self-validation, run with `pytest`.
