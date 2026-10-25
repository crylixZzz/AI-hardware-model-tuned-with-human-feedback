"""Statistical primitives shared by the gap and evaluation analyses.

Nothing here reads a threshold; callers pass ``alpha``, bootstrap counts, and seeds
from ``thresholds.yaml``. AUROC differences between two correlated classifiers use the
fast DeLong estimator; paired disagreement uses McNemar; family-wise correction uses
Holm-Bonferroni.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import stats
from sklearn.metrics import average_precision_score, roc_auc_score
from statsmodels.stats.contingency_tables import mcnemar as _sm_mcnemar
from statsmodels.stats.multitest import multipletests


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float


def auroc(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, scores))


def auprc(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, scores))


def bootstrap_metric_ci(
    y_true: np.ndarray,
    scores: np.ndarray,
    metric: Callable[[np.ndarray, np.ndarray], float],
    iterations: int,
    alpha: float,
    seed: int,
) -> Interval:
    rng = np.random.default_rng(seed)
    n = len(y_true)
    point = metric(y_true, scores)
    samples = np.empty(iterations)
    for i in range(iterations):
        idx = rng.integers(0, n, n)
        samples[i] = metric(y_true[idx], scores[idx])
    lo, hi = np.nanpercentile(samples, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return Interval(point=point, low=float(lo), high=float(hi))


def bootstrap_metric_diff_ci(
    y_true: np.ndarray,
    scores_a: np.ndarray,
    scores_b: np.ndarray,
    metric: Callable[[np.ndarray, np.ndarray], float],
    iterations: int,
    alpha: float,
    seed: int,
) -> Interval:
    """CI on metric(a) - metric(b) under the paired bootstrap (same resampled indices
    for both classifiers, so their correlation is preserved)."""
    rng = np.random.default_rng(seed)
    n = len(y_true)
    point = metric(y_true, scores_a) - metric(y_true, scores_b)
    samples = np.empty(iterations)
    for i in range(iterations):
        idx = rng.integers(0, n, n)
        yt = y_true[idx]
        samples[i] = metric(yt, scores_a[idx]) - metric(yt, scores_b[idx])
    lo, hi = np.nanpercentile(samples, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return Interval(point=float(point), low=float(lo), high=float(hi))


def bootstrap_rate_ci(indicator: np.ndarray, iterations: int, alpha: float, seed: int) -> Interval:
    rng = np.random.default_rng(seed)
    n = len(indicator)
    point = float(np.mean(indicator)) if n else float("nan")
    if n == 0:
        return Interval(point, float("nan"), float("nan"))
    samples = np.empty(iterations)
    for i in range(iterations):
        idx = rng.integers(0, n, n)
        samples[i] = np.mean(indicator[idx])
    lo, hi = np.percentile(samples, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return Interval(point=point, low=float(lo), high=float(hi))


@dataclass(frozen=True)
class McNemarResult:
    n01: int
    n10: int
    statistic: float
    pvalue: float


def mcnemar_discordant(n_over: int, n_under: int) -> McNemarResult:
    """McNemar from the two discordant cell counts directly. Used for the oracle-vs-
    hardware table where ``n_over`` = predicted reliable but failed (optimistic) and
    ``n_under`` = predicted unreliable but passed."""
    if n_over + n_under == 0:
        return McNemarResult(n_over, n_under, float("nan"), 1.0)
    exact = (n_over + n_under) < 25
    res = _sm_mcnemar(np.array([[0, n_over], [n_under, 0]]), exact=exact, correction=not exact)
    return McNemarResult(n01=n_over, n10=n_under, statistic=float(res.statistic), pvalue=float(res.pvalue))


def holm_bonferroni(pvalues: list[float], alpha: float) -> tuple[list[bool], list[float]]:
    if not pvalues:
        return [], []
    reject, adjusted, _, _ = multipletests(pvalues, alpha=alpha, method="holm")
    return list(reject), [float(p) for p in adjusted]


def _midrank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x)
    ranked = x[order]
    n = len(x)
    out = np.zeros(n)
    i = 0
    while i < n:
        j = i
        while j < n and ranked[j] == ranked[i]:
            j += 1
        out[i:j] = 0.5 * (i + j - 1) + 1
        i = j
    result = np.empty(n)
    result[order] = out
    return result


def _fast_delong(predictions: np.ndarray, positives: int) -> tuple[np.ndarray, np.ndarray]:
    m = positives
    n = predictions.shape[1] - m
    pos = predictions[:, :m]
    neg = predictions[:, m:]
    k = predictions.shape[0]
    tx = np.empty((k, m))
    ty = np.empty((k, n))
    tz = np.empty((k, m + n))
    for r in range(k):
        tx[r] = _midrank(pos[r])
        ty[r] = _midrank(neg[r])
        tz[r] = _midrank(predictions[r])
    aucs = tz[:, :m].sum(axis=1) / m / n - (m + 1.0) / 2.0 / n
    v01 = (tz[:, :m] - tx) / n
    v10 = 1.0 - (tz[:, m:] - ty) / m
    cov = np.cov(v01) / m + np.cov(v10) / n
    return aucs, np.atleast_2d(cov)


@dataclass(frozen=True)
class DeLongResult:
    auc_a: float
    auc_b: float
    z: float
    pvalue: float


def delong_auroc_test(y_true: np.ndarray, scores_a: np.ndarray, scores_b: np.ndarray) -> DeLongResult:
    """Two-sided DeLong test for AUROC(a) != AUROC(b) on the same labels."""
    y_true = np.asarray(y_true).astype(int)
    if len(np.unique(y_true)) < 2:
        return DeLongResult(float("nan"), float("nan"), float("nan"), float("nan"))
    order = np.argsort(-y_true)
    positives = int(y_true.sum())
    predictions = np.vstack((scores_a, scores_b))[:, order]
    aucs, cov = _fast_delong(predictions, positives)
    contrast = np.array([[1.0, -1.0]])
    var = float((contrast @ cov @ contrast.T)[0, 0])
    if var <= 0:
        return DeLongResult(float(aucs[0]), float(aucs[1]), float("nan"), float("nan"))
    z = float((aucs[0] - aucs[1]) / np.sqrt(var))
    return DeLongResult(float(aucs[0]), float(aucs[1]), z, float(2 * stats.norm.sf(abs(z))))
