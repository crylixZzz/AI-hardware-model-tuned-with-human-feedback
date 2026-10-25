"""The gap: how often the cheap oracles' optimistic verdict diverges from hardware.

Per failure class we count over-prediction (predicted reliable, failed on hardware)
and under-prediction (predicted unreliable, passed), bootstrap a CI on the
over-prediction rate, and test the paired disagreement with McNemar. The McNemar
p-values are corrected across classes with Holm-Bonferroni. Censored-unknown records
carry no hardware label and are excluded here rather than counted as passes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Thresholds
from ..schemas import FAILURE_CLASSES
from . import stats


def _usable(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["hardware_reliable"].notna()]


def gap_analysis(frame: pd.DataFrame, thresholds: Thresholds) -> dict:
    an = thresholds.analysis
    usable = _usable(frame)

    per_class: dict[str, dict] = {}
    pvalues: list[float] = []
    class_order: list[str] = []

    for fc in FAILURE_CLASSES:
        sub = usable[usable["failure_class"] == fc]
        if sub.empty:
            continue
        oracle_reliable = sub["oracle_predicted_reliable"].astype(bool).to_numpy()
        hw_reliable = sub["hardware_reliable"].astype(bool).to_numpy()

        over = oracle_reliable & ~hw_reliable
        under = ~oracle_reliable & hw_reliable
        n_over, n_under = int(over.sum()), int(under.sum())

        over_ci = stats.bootstrap_rate_ci(over.astype(int), an.bootstrap_iterations, an.alpha, an.bootstrap_seed)
        mcn = stats.mcnemar_discordant(n_over, n_under)

        predicted_reliable = sub[oracle_reliable]
        false_reassurance = float(np.mean(~predicted_reliable["hardware_reliable"].astype(bool))) if len(predicted_reliable) else float("nan")

        per_class[fc] = {
            "n_usable": int(len(sub)),
            "n_hardware_failures": int((~hw_reliable).sum()),
            "n_censored_excluded": int((frame["failure_class"] == fc).sum() - len(sub)),
            "oracle_reliable_rate": float(oracle_reliable.mean()),
            "hardware_reliable_rate": float(hw_reliable.mean()),
            "over_prediction_rate": {"point": over_ci.point, "low": over_ci.low, "high": over_ci.high},
            "under_prediction_rate": float(under.mean()),
            "false_reassurance_rate": false_reassurance,
            "mcnemar": {"n_over": mcn.n01, "n_under": mcn.n10, "statistic": mcn.statistic, "pvalue": mcn.pvalue},
        }
        pvalues.append(mcn.pvalue)
        class_order.append(fc)

    reject, adjusted = stats.holm_bonferroni(pvalues, an.alpha)
    for fc, rej, adj in zip(class_order, reject, adjusted):
        per_class[fc]["mcnemar"]["pvalue_holm"] = adj
        per_class[fc]["mcnemar"]["significant"] = bool(rej)

    return {
        "n_usable": int(len(usable)),
        "n_total": int(len(frame)),
        "n_censored_excluded": int(len(frame) - len(usable)),
        "alpha": an.alpha,
        "per_class": per_class,
    }
