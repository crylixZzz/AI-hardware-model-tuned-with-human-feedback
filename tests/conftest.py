from pathlib import Path

import pytest

from oraclegap import analysis, pipeline
from oraclegap.config import Paths, load_config
from oraclegap.data.store import DatasetStore

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cfg(tmp_path_factory):
    """Config pointing at an isolated dataset tree so tests never touch repo data."""
    base = tmp_path_factory.mktemp("oraclegap_data")
    config = load_config(REPO_ROOT / "config" / "default.yaml", REPO_ROOT)
    config.paths = Paths(
        dataset=str(base / "dataset"),
        artifacts=str(base / "artifacts"),
        runs=str(base / "runs"),
    )
    return config


@pytest.fixture(scope="session")
def mock_dataset(cfg):
    """Run the full mock pipeline once and return the assembled frame."""
    pipeline.run_generation(cfg, "mock")
    pipeline.run_oracles(cfg, "mock")
    pipeline.run_hardware(cfg, "mock")
    pipeline.build_dataset(cfg, "mock")
    records = DatasetStore(cfg.repo_root / cfg.paths.dataset / "mock", "mock").read_records()
    return analysis.records_to_frame(records)
