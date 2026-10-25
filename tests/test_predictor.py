import math

from oraclegap.predictor.evaluate import evaluate


def _reduced(cfg):
    thresholds = cfg.thresholds.model_copy(deep=True)
    thresholds.analysis.bootstrap_iterations = 400
    return thresholds


def test_predictor_beats_best_single_oracle_on_both_splits(cfg, mock_dataset):
    report = evaluate(mock_dataset, _reduced(cfg))
    assert report["n_failures"] < report["n_usable"] / 2  # minority positive class

    for split in ("family", "random"):
        block = report["splits"][split]
        best_auroc = block["oracles"][block["best_single_oracle"]]["auroc"]
        logistic = block["predictors"]["logistic"]
        assert logistic["auroc"] > best_auroc
        assert not math.isnan(logistic["auprc"])

    # The family split is the honest headline: the margin is positive and the DeLong
    # test on the AUROC difference is significant (bootstrap-independent, so stable).
    family_vs_best = report["splits"]["family"]["predictors"]["logistic"]["vs_best_oracle"]
    assert family_vs_best["auroc_diff_ci"]["point"] > 0.0
    assert family_vs_best["delong"]["pvalue"] < 0.05
