from pathlib import Path

from oraclegap.config import load_config
from oraclegap.validation.self_test import run_self_validation

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fresh_cfg():
    return load_config(REPO_ROOT / "config" / "default.yaml", REPO_ROOT)


def test_planted_failures_are_all_detected():
    report = run_self_validation(_fresh_cfg(), "mock")
    assert report.ok, [(r.task_id, r.name, r.expected, r.actual) for r in report.failures()]
    # Every class ships at least a clean reference and one planted failure.
    assert len(report.results) >= 10


def test_gate_fails_when_the_instrument_is_broken():
    # Blind the functional criterion. The planted functional failure must then slip
    # through, and the self-validation gate must notice and fail loudly. If it did not,
    # the gate would be decorative.
    cfg = _fresh_cfg()
    cfg.thresholds.functional.min_pass_rate = 0.0
    report = run_self_validation(cfg, "mock")
    assert not report.ok
    missed = {r.name for r in report.failures()}
    assert "buffer_overflow_longrun" in missed
