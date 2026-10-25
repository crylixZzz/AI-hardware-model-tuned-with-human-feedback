"""Predictor evaluation.

The headline split is by task family: train on some families, test on families held
out entirely, so a reported edge over the oracles is not memorized per task. A random
split is reported alongside precisely because it is the leakage-prone comparison and
the honest number is expected to be lower. Failures are the minority positive class,
so AUPRC is reported next to AUROC, and the predictor is compared to the best single
cheap oracle and to confidence alone with bootstrap CIs on the difference and a DeLong
test on the AUROC gap.
"""

from __future__ import annotations

import numpy as np
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold

from ..config import AnalysisThresholds
from .features import Dataset, build_dataset, oracle_failure_scores
from .train import make_model, predict_failure_proba

# The composite oracle rule is not a single oracle; the "best single cheap oracle"
# baseline is the strongest of the atomic ones.
_ATOMIC_ORACLES = (
    "unit_tests",
    "static_findings",
    "static_warnings",
    "emulation_timing",
    "confidence_verbalized",
    "confidence_logprob",
)
_PREDICTOR_KINDS = ("gbt", "logistic")


def _oof_predictions(ds: Dataset, kind: str, split: str, seed: int) -> np.ndarray:
    pred = np.full(len(ds.y), np.nan)
    if split == "family":
        folds = list(LeaveOneGroupOut().split(ds.X, ds.y, ds.groups))
    elif split == "random":
        folds = list(StratifiedKFold(n_splits=5, shuffle=True, random_state=seed).split(ds.X, ds.y))
    else:
        raise ValueError(f"unknown split: {split!r}")
    for train_idx, test_idx in folds:
        if len(np.unique(ds.y[train_idx])) < 2:
            continue
        model = make_model(kind)
        model.fit(ds.X.iloc[train_idx], ds.y[train_idx])
        pred[test_idx] = predict_failure_proba(model, ds.X.iloc[test_idx])
    return pred


def _metric_block(y, scores, an: AnalysisThresholds):
    from ..analysis import stats

    return {
        "auroc": stats.auroc(y, scores),
        "auprc": stats.auprc(y, scores),
        "auroc_ci": _interval(stats.bootstrap_metric_ci(y, scores, stats.auroc, an.bootstrap_iterations, an.alpha, an.bootstrap_seed)),
        "auprc_ci": _interval(stats.bootstrap_metric_ci(y, scores, stats.auprc, an.bootstrap_iterations, an.alpha, an.bootstrap_seed)),
    }


def _comparison(y, pred, baseline, an: AnalysisThresholds):
    from ..analysis import stats

    delong = stats.delong_auroc_test(y, pred, baseline)
    auroc_diff = stats.bootstrap_metric_diff_ci(y, pred, baseline, stats.auroc, an.bootstrap_iterations, an.alpha, an.bootstrap_seed)
    auprc_diff = stats.bootstrap_metric_diff_ci(y, pred, baseline, stats.auprc, an.bootstrap_iterations, an.alpha, an.bootstrap_seed)
    return {
        "delong": {"auc_predictor": delong.auc_a, "auc_baseline": delong.auc_b, "z": delong.z, "pvalue": delong.pvalue},
        "auroc_diff_ci": _interval(auroc_diff),
        "auprc_diff_ci": _interval(auprc_diff),
    }


def _interval(iv) -> dict[str, float]:
    return {"point": iv.point, "low": iv.low, "high": iv.high}


def evaluate(frame, thresholds) -> dict:
    an: AnalysisThresholds = thresholds.analysis
    ds = build_dataset(frame)
    if len(np.unique(ds.y)) < 2:
        raise RuntimeError("evaluation needs both reliable and failing records")

    oracle_scores = oracle_failure_scores(ds.frame)
    report: dict = {
        "n_usable": int(len(ds.y)),
        "n_failures": int(ds.y.sum()),
        "splits": {},
    }

    for split in ("family", "random"):
        oracle_metrics = {name: _metric_block(ds.y, oracle_scores[name], an) for name in _ATOMIC_ORACLES}
        best_oracle = max(
            (n for n in _ATOMIC_ORACLES if not np.isnan(oracle_metrics[n]["auroc"])),
            key=lambda n: oracle_metrics[n]["auroc"],
        )
        best_scores = oracle_scores[best_oracle]
        confidence_scores = oracle_scores["confidence_verbalized"]

        predictors: dict = {}
        for kind in _PREDICTOR_KINDS:
            pred = _oof_predictions(ds, kind, split, an.bootstrap_seed)
            mask = ~np.isnan(pred)
            yv, pv = ds.y[mask], pred[mask]
            predictors[kind] = {
                **_metric_block(yv, pv, an),
                "vs_best_oracle": _comparison(yv, pv, best_scores[mask], an),
                "vs_confidence": _comparison(yv, pv, confidence_scores[mask], an),
            }

        report["splits"][split] = {
            "oracles": oracle_metrics,
            "oracle_rule": _metric_block(ds.y, oracle_scores["oracle_rule"], an),
            "best_single_oracle": best_oracle,
            "predictors": predictors,
        }
    return report
