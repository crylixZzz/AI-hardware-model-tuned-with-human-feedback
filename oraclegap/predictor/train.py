"""Reliability predictor models.

Gradient-boosted trees and logistic regression are the primaries: interpretable and
honest at this data scale. The trees handle the feature interactions (finding counts
by failure class, emulated-timing by class) that let the predictor recover the hidden
hazard a single oracle cannot. An optional torch MLP is available as a secondary only.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PredictorKind = str  # "gbt" | "logistic" | "mlp"
_SEED = 0


def make_model(kind: PredictorKind):
    if kind == "gbt":
        return HistGradientBoostingClassifier(
            max_depth=2,
            learning_rate=0.05,
            max_iter=200,
            l2_regularization=2.0,
            min_samples_leaf=25,
            random_state=_SEED,
        )
    if kind == "logistic":
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            # liblinear is stable on this small, nearly-separable data where LBFGS
            # overflows during line search.
            ("clf", LogisticRegression(solver="liblinear", C=0.5, class_weight="balanced")),
        ])
    if kind == "mlp":
        return _make_mlp()
    raise ValueError(f"unknown predictor kind: {kind!r}")


def predict_failure_proba(model, X) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def _make_mlp():
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", _TorchMLP()),
    ])


class _TorchMLP:
    """Minimal two-layer torch classifier with an sklearn-compatible surface, so it
    drops into the same evaluation harness as the primaries. Secondary only."""

    def __init__(self, hidden: tuple[int, int] = (32, 16), epochs: int = 400, lr: float = 1e-2) -> None:
        self._hidden = hidden
        self._epochs = epochs
        self._lr = lr
        self._net = None

    def fit(self, X, y):
        import torch
        from torch import nn

        torch.manual_seed(_SEED)
        xt = torch.tensor(np.asarray(X, dtype=np.float32))
        yt = torch.tensor(np.asarray(y, dtype=np.float32)).unsqueeze(1)
        h1, h2 = self._hidden
        self._net = nn.Sequential(
            nn.Linear(xt.shape[1], h1), nn.ReLU(),
            nn.Linear(h1, h2), nn.ReLU(),
            nn.Linear(h2, 1),
        )
        pos_weight = torch.tensor([(len(y) - y.sum()) / max(1, y.sum())], dtype=torch.float32)
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        opt = torch.optim.Adam(self._net.parameters(), lr=self._lr)
        for _ in range(self._epochs):
            opt.zero_grad()
            loss_fn(self._net(xt), yt).backward()
            opt.step()
        return self

    def predict_proba(self, X):
        import torch

        with torch.no_grad():
            logits = self._net(torch.tensor(np.asarray(X, dtype=np.float32)))
            p = torch.sigmoid(logits).numpy().ravel()
        return np.column_stack([1.0 - p, p])
