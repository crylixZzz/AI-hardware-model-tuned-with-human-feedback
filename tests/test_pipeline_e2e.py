def test_dataset_shape_and_balance(cfg, mock_dataset):
    frame = mock_dataset
    assert len(frame) == cfg.k * 5 * len(cfg.models)
    assert (frame["source"] == "mock").all()

    reliable = frame["hardware_reliable"]
    assert reliable.eq(True).any() and reliable.eq(False).any()
    fail_rate = reliable.eq(False).mean()
    assert 0.0 < fail_rate < 0.5  # failures are the minority class

    # Soak programs that survive the window are censored-but-reliable, not plain passes.
    assert frame["censored"].any()
