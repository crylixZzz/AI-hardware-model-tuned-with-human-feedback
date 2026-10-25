"""Ground-truth orchestration: run the hardware backends for a task's failure class
and convert their raw measurements into a labelled :class:`ClassOutcome` using the
pre-registered thresholds.

This layer is the scientific instrument. It holds no measurement logic of its own --
it only dispatches to capture backends and applies the config thresholds -- so that
the self-validation suite can exercise exactly this threshold logic against planted,
known-answer captures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import RunConfig
from ..hardware.concurrency import make_concurrency_stressor
from ..hardware.functional import make_functional_runner
from ..hardware.peripheral import make_peripheral_probe
from ..hardware.soak import make_soak_monitor
from ..hardware.timing import make_timing_capture
from ..mock import Injection, LatentDraw, draw_latent
from ..schemas import ClassOutcome, FailureClass, GroundTruth, Source
from ..taskset import TaskMeta

# Measurement-protocol windows (seconds). These are how long each instrument observes,
# not pass/fail thresholds; the latter live only in thresholds.yaml.
_TIMING_WINDOW_S = 10.0
_CONCURRENCY_WINDOW_S = 30.0


def _emulation_measures_timing(cfg: RunConfig) -> bool:
    return cfg.emulation_backend in ("qemu", "mock")


def _write_artifact(artifact_dir: Optional[Path], record_id: str, failure_class: str, payload: dict) -> Optional[str]:
    if artifact_dir is None:
        return None
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{record_id}.{failure_class}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return str(path)


def _functional_outcome(cfg, runner, artifact_dir, record_id) -> ClassOutcome:
    m = runner.run()
    reliable = m.pass_rate >= cfg.thresholds.functional.min_pass_rate
    measurements = {"pass_rate": m.pass_rate, "tests_total": float(m.tests_total), "tests_passed": float(m.tests_passed)}
    artifact = _write_artifact(artifact_dir, record_id, "functional", {"backend": runner.backend_name, **measurements})
    return ClassOutcome(
        failure_class="functional",
        outcome="pass" if reliable else "fail",
        measurements=measurements,
        raw_artifact=artifact,
    )


def _timing_outcome(cfg, capture, deadline_us, artifact_dir, record_id) -> ClassOutcome:
    m = capture.capture(_TIMING_WINDOW_S, deadline_us or 1000.0)
    measurements = {"deadline_miss_rate": m.deadline_miss_rate, "jitter_us": m.jitter_us, "samples": float(m.samples)}
    artifact = _write_artifact(artifact_dir, record_id, "timing", {"backend": capture.backend_name, **measurements})
    if m.truncated:
        return ClassOutcome(failure_class="timing", outcome="censored_unknown", measurements=measurements, raw_artifact=artifact)
    t = cfg.thresholds.timing
    reliable = m.deadline_miss_rate <= t.max_deadline_miss_rate and m.jitter_us <= t.max_jitter_us
    return ClassOutcome(
        failure_class="timing",
        outcome="pass" if reliable else "fail",
        measurements=measurements,
        raw_artifact=artifact,
    )


def _concurrency_outcome(cfg, stressor, artifact_dir, record_id) -> ClassOutcome:
    m = stressor.stress(_CONCURRENCY_WINDOW_S)
    measurements = {"race_events": float(m.race_events), "stress_duration_s": m.stress_duration_s}
    artifact = _write_artifact(artifact_dir, record_id, "concurrency", {"backend": stressor.backend_name, **measurements})
    reliable = m.race_events <= cfg.thresholds.concurrency.max_race_events
    return ClassOutcome(
        failure_class="concurrency",
        outcome="pass" if reliable else "fail",
        measurements=measurements,
        raw_artifact=artifact,
    )


def _soak_outcome(cfg, monitor, artifact_dir, record_id) -> ClassOutcome:
    required_s = cfg.thresholds.resource_soak.required_hours * 3600.0
    m = monitor.monitor(required_s)
    # Omit time_to_failure_s when nothing failed rather than storing NaN: the record
    # ledger is JSON, and a NaN would serialize to null and break the float round-trip.
    measurements = {"observed_window_s": m.observed_window_s}
    if m.time_to_failure_s is not None:
        measurements["time_to_failure_s"] = m.time_to_failure_s
    artifact = _write_artifact(
        artifact_dir, record_id, "resource_soak",
        {"backend": monitor.backend_name, "failure_kind": m.failure_kind, **measurements},
    )
    if m.aborted:
        outcome = "censored_unknown"
    elif m.time_to_failure_s is None:
        # Survived to the end of observation. Only a pass if that reached the required window.
        outcome = "censored_survived" if m.observed_window_s >= required_s else "censored_unknown"
    elif m.time_to_failure_s >= required_s:
        outcome = "pass"  # failure observed, but only after surviving the required window
    else:
        outcome = "fail"
    return ClassOutcome(failure_class="resource_soak", outcome=outcome, measurements=measurements, raw_artifact=artifact)


def _peripheral_outcome(cfg, probe, artifact_dir, record_id) -> ClassOutcome:
    m = probe.probe()
    measurements = {"edge_failures": float(m.edge_failures), "edge_total": float(m.edge_total)}
    artifact = _write_artifact(artifact_dir, record_id, "peripheral_edge", {"backend": probe.backend_name, **measurements})
    reliable = m.edge_failures <= cfg.thresholds.peripheral_edge.max_edge_failures
    return ClassOutcome(
        failure_class="peripheral_edge",
        outcome="pass" if reliable else "fail",
        measurements=measurements,
        raw_artifact=artifact,
    )


def run_ground_truth(
    cfg: RunConfig,
    source: Source,
    task: TaskMeta,
    model_id: str,
    sample_index: int,
    record_id: str,
    injection: Optional[Injection] = None,
    artifact_dir: Optional[Path] = None,
) -> GroundTruth:
    """Measure the task's failure class on the ground-truth path and label it.

    ``injection`` plants a known defect (self-validation) and forces exact mock
    measurements; it is only honoured when ``source == 'mock'``.
    """
    latent: Optional[LatentDraw] = None
    if source == "mock" and injection is None:
        latent = draw_latent(
            seed=cfg.seed,
            task_id=task.id,
            model_id=model_id,
            sample_index=sample_index,
            failure_class=task.failure_class,
            difficulty=task.difficulty,
            emulation_measures_timing=_emulation_measures_timing(cfg),
        )

    fc: FailureClass = task.failure_class
    if fc == "functional":
        runner = make_functional_runner(cfg, source, latent=latent, injection=injection)
        outcome = _functional_outcome(cfg, runner, artifact_dir, record_id)
    elif fc == "timing":
        capture = make_timing_capture(cfg, source, latent=latent, injection=injection)
        outcome = _timing_outcome(cfg, capture, task.deadline_us, artifact_dir, record_id)
    elif fc == "concurrency":
        stressor = make_concurrency_stressor(cfg, source, latent=latent, injection=injection)
        outcome = _concurrency_outcome(cfg, stressor, artifact_dir, record_id)
    elif fc == "resource_soak":
        monitor = make_soak_monitor(cfg, source, latent=latent, injection=injection)
        outcome = _soak_outcome(cfg, monitor, artifact_dir, record_id)
    elif fc == "peripheral_edge":
        probe = make_peripheral_probe(cfg, source, latent=latent, injection=injection)
        outcome = _peripheral_outcome(cfg, probe, artifact_dir, record_id)
    else:  # pragma: no cover - exhaustive over FailureClass
        raise ValueError(f"unhandled failure class: {fc}")

    return GroundTruth(outcomes=[outcome])
