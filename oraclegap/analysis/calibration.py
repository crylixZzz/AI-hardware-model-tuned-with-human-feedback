"""Calibration of model confidence against the hardware outcome.

Treats verbalized confidence/100 as the model's stated probability that the program
is reliable and scores it against the realized hardware label with the Brier score and
expected calibration error (ECE). A large positive mean gap (confidence minus realized
reliability) is overconfidence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def reliability_calibration(frame: pd.DataFrame, n_bins: int = 10) -> dict:
    usable = frame[frame["hardware_reliable"].notna() & frame["confidence_verbalized"].notna()]
    if usable.empty:
        return {"n": 0}

    confidence = usable["confidence_verbalized"].to_numpy() / 100.0
    reliable = usable["hardware_reliable"].astype(bool).to_numpy().astype(float)

    brier = float(np.mean((confidence - reliable) ** 2))

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.clip(np.digitize(confidence, edges[1:-1]), 0, n_bins - 1)
    ece = 0.0
    bins: list[dict] = []
    for b in range(n_bins):
        mask = bin_idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        mean_conf = float(confidence[mask].mean())
        observed = float(reliable[mask].mean())
        ece += count / len(confidence) * abs(mean_conf - observed)
        bins.append({"bin": b, "count": count, "mean_confidence": mean_conf, "observed_reliable": observed})

    return {
        "n": int(len(usable)),
        "brier": brier,
        "ece": float(ece),
        "mean_confidence": float(confidence.mean()),
        "mean_reliable": float(reliable.mean()),
        "overconfidence": float(confidence.mean() - reliable.mean()),
        "bins": bins,
    }
