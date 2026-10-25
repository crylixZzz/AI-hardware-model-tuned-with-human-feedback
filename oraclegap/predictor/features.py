"""Feature extraction for the reliability predictor.

Every feature is available before deployment -- static findings, cheap-oracle results,
model confidence, and task metadata. Nothing derived from the hardware outcome enters
the matrix; that separation is what keeps the predictor honest. Records whose hardware
label is censored-unknown carry no target and are dropped here, not imputed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_NUMERIC = [
    "unit_test_pass_rate",
    "n_findings_error",
    "n_findings_warning",
    "n_findings_info",
    "n_findings_total",
    "emu_jitter_us",
    "emu_deadline_miss_rate",
    "confidence_verbalized",
    "confidence_logprob",
]
_BINARY = ["emulation_functional", "emu_has_timing", "open_weight"]


@dataclass(frozen=True)
class Dataset:
    X: pd.DataFrame
    y: np.ndarray  # 1 = hardware failure (the minority, positive class)
    groups: np.ndarray  # task_family, for family-split
    frame: pd.DataFrame  # usable rows, aligned with X/y


def usable_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows with a decided hardware label. ``hardware_reliable`` is a nullable boolean;
    NA marks censored-unknown runs, which cannot serve as training targets."""
    return frame[frame["hardware_reliable"].notna()].reset_index(drop=True)


def build_dataset(frame: pd.DataFrame) -> Dataset:
    usable = usable_rows(frame)
    X = pd.DataFrame(index=usable.index)
    for col in _NUMERIC:
        X[col] = usable[col].astype(float)
    for col in _BINARY:
        X[col] = usable[col].astype(float)
    # Task failure class and family are deliberately excluded. Both are known before
    # deployment, but keying on them teaches a class-specific base rate that cannot
    # transfer to a held-out family; the predictor must earn its score from signals
    # whose relationship to failure is class-independent (static warnings, confidence,
    # emulated timing), which is exactly what the family split tests.

    y = (~usable["hardware_reliable"].astype(bool)).to_numpy().astype(int)
    groups = usable["task_family"].to_numpy()
    return Dataset(X=X, y=y, groups=groups, frame=usable)


def oracle_failure_scores(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Per-oracle score oriented so that higher means more likely to fail on hardware.
    These are the single-oracle baselines the learned predictor must beat."""
    conf = frame["confidence_verbalized"].to_numpy()
    conf_score = np.where(np.isnan(conf), 0.5, (100.0 - conf) / 100.0)
    logprob = frame["confidence_logprob"].to_numpy()
    logprob_score = np.where(np.isnan(logprob), np.nanmedian(logprob), -logprob)
    jitter = frame["emu_jitter_us"].to_numpy()
    jitter_score = np.where(np.isnan(jitter), 0.0, jitter)
    return {
        "unit_tests": 1.0 - frame["unit_test_pass_rate"].to_numpy(),
        "static_findings": frame["n_findings_total"].to_numpy().astype(float),
        "static_warnings": frame["n_findings_warning"].to_numpy().astype(float),
        "emulation_timing": jitter_score,
        "confidence_verbalized": conf_score,
        "confidence_logprob": logprob_score,
        "oracle_rule": (~frame["oracle_predicted_reliable"].astype(bool)).to_numpy().astype(float),
    }
