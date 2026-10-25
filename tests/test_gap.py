from oraclegap.analysis import gap_analysis


def _reduced(cfg):
    thresholds = cfg.thresholds.model_copy(deep=True)
    thresholds.analysis.bootstrap_iterations = 400
    return thresholds


def test_gap_is_concentrated_off_functional(cfg, mock_dataset):
    gap = gap_analysis(mock_dataset, _reduced(cfg))
    per_class = gap["per_class"]

    significant = {fc for fc, row in per_class.items() if row["mcnemar"]["significant"]}
    assert {"timing", "concurrency", "resource_soak"} <= significant

    # The functional oracle tracks hardware, so it barely over-predicts; non-functional
    # classes over-predict much more. That contrast is the result the project exists to show.
    functional_over = per_class["functional"]["over_prediction_rate"]["point"]
    assert functional_over < per_class["timing"]["over_prediction_rate"]["point"]


def test_censored_accounting_is_explicit(cfg, mock_dataset):
    gap = gap_analysis(mock_dataset, _reduced(cfg))
    usable = mock_dataset["hardware_reliable"].notna().sum()
    assert gap["n_usable"] == usable
    assert gap["n_censored_excluded"] == len(mock_dataset) - usable
