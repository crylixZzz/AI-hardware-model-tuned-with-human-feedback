from oraclegap.analysis import reliability_calibration
from oraclegap.mock import draw_latent


def test_confidence_is_overconfident(cfg, mock_dataset):
    cal = reliability_calibration(mock_dataset)
    assert cal["n"] > 0
    assert 0.0 <= cal["brier"] <= 1.0
    assert cal["ece"] > 0.1
    assert cal["overconfidence"] > 0.1  # states more reliability than hardware delivers


def test_latent_draw_is_deterministic():
    args = dict(
        seed=7, task_id="t", model_id="m", sample_index=3,
        failure_class="timing", difficulty="hard", emulation_measures_timing=True,
    )
    a = draw_latent(**args)
    b = draw_latent(**args)
    assert a == b

    c = draw_latent(**{**args, "seed": 8})
    assert a != c
