"""Append-only, schema-validated dataset store.

Two JSONL ledgers (generation samples and assembled program records) plus a Parquet
export of the flattened records for analysis. The store is opened for one ``source``
and refuses any record whose ``source`` disagrees, which is the concrete enforcement
of "measurements come only from the path named by the source field": a mock run can
never append into a real dataset or vice versa.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from ..schemas import GenerationSample, ProgramRecord, Source


class SourceMismatch(ValueError):
    pass


class DatasetStore:
    def __init__(self, root: str | Path, source: Source) -> None:
        self.root = Path(root)
        self.source = source
        self.root.mkdir(parents=True, exist_ok=True)
        self.generation_path = self.root / "generation.jsonl"
        self.records_path = self.root / "records.jsonl"
        self.parquet_path = self.root / "records.parquet"

    def _guard(self, declared: Source) -> None:
        if declared != self.source:
            raise SourceMismatch(
                f"store opened for source={self.source!r} but record declares {declared!r}"
            )

    def append_generation(self, samples: Iterable[GenerationSample]) -> int:
        n = 0
        with self.generation_path.open("a") as fh:
            for sample in samples:
                self._guard(sample.source)
                fh.write(sample.model_dump_json() + "\n")
                n += 1
        return n

    def append_records(self, records: Iterable[ProgramRecord]) -> int:
        n = 0
        with self.records_path.open("a") as fh:
            for record in records:
                self._guard(record.source)
                fh.write(record.model_dump_json() + "\n")
                n += 1
        return n

    def read_generation(self) -> list[GenerationSample]:
        if not self.generation_path.exists():
            return []
        return [GenerationSample.model_validate_json(line) for line in _nonempty_lines(self.generation_path)]

    def read_records(self) -> list[ProgramRecord]:
        if not self.records_path.exists():
            return []
        return [ProgramRecord.model_validate_json(line) for line in _nonempty_lines(self.records_path)]

    def export_parquet(self) -> Path:
        frame = records_to_frame(self.read_records())
        frame.to_parquet(self.parquet_path, index=False)
        return self.parquet_path


def _nonempty_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


_MEASUREMENT_COLUMNS = (
    "pass_rate",
    "deadline_miss_rate",
    "jitter_us",
    "race_events",
    "time_to_failure_s",
    "edge_failures",
)


def flatten_record(record: ProgramRecord) -> dict[str, object]:
    oracles = record.oracles
    severities = [f.severity for f in oracles.static_findings]
    primary = record.ground_truth.outcomes[0]
    emu = oracles.emulation_timing

    row: dict[str, object] = {
        "record_id": record.record_id,
        "task_id": record.task_id,
        "task_family": record.task_family,
        "failure_class": record.failure_class,
        "model_id": record.model_id,
        "open_weight": record.open_weight,
        "sample_index": record.sample_index,
        "difficulty": record.difficulty,
        "source": record.source,
        "unit_test_pass_rate": oracles.unit_test_pass_rate,
        "unit_tests_total": oracles.unit_tests_total,
        "unit_tests_passed": oracles.unit_tests_passed,
        "n_findings_error": severities.count("error"),
        "n_findings_warning": severities.count("warning"),
        "n_findings_info": severities.count("info"),
        "n_findings_total": len(severities),
        "emulation_functional": oracles.emulation_functional,
        "emu_has_timing": emu is not None,
        "emu_jitter_us": emu.jitter_us if emu else float("nan"),
        "emu_deadline_miss_rate": emu.deadline_miss_rate if emu else float("nan"),
        "confidence_verbalized": oracles.confidence_verbalized if oracles.confidence_verbalized is not None else float("nan"),
        "confidence_logprob": oracles.confidence_logprob if oracles.confidence_logprob is not None else float("nan"),
        "oracle_predicted_reliable": record.oracle_predicted_reliable,
        "hardware_reliable": record.hardware_reliable,
        "outcome_status": primary.outcome,
        "censored": primary.censored,
    }
    for col in _MEASUREMENT_COLUMNS:
        row[f"meas_{col}"] = primary.measurements.get(col, float("nan"))
    return row


def records_to_frame(records: list[ProgramRecord]) -> pd.DataFrame:
    frame = pd.DataFrame([flatten_record(r) for r in records])
    if not frame.empty:
        frame["hardware_reliable"] = frame["hardware_reliable"].astype("boolean")
    return frame
