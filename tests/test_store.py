import pytest

from oraclegap.data.store import DatasetStore, SourceMismatch, records_to_frame
from tests.test_schemas import _record


def test_source_guard_rejects_cross_source_write(tmp_path):
    store = DatasetStore(tmp_path / "ds", source="real")
    with pytest.raises(SourceMismatch):
        store.append_records([_record("fail", source="mock")])


def test_append_read_round_trip_and_parquet(tmp_path):
    store = DatasetStore(tmp_path / "ds", source="mock")
    store.append_records([_record("fail"), _record("pass")])
    assert len(store.read_records()) == 2
    parquet = store.export_parquet()
    assert parquet.exists()
    frame = records_to_frame(store.read_records())
    assert set(frame["hardware_reliable"].dropna()) <= {True, False}
