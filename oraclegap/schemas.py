"""Record schemas for the Oracle Gap dataset.

Every measurement in this project flows through these models. Two invariants are
load-bearing for scientific validity and are enforced here rather than by convention:

- ``source`` ("real" | "mock") names the execution path that produced a record.
  Mixing the two in one analysis is a category error; the store (``data/store.py``)
  refuses writes where ``source`` disagrees with the backend that ran.
- Right-censored timing/soak observations are represented explicitly. A run that
  ended before a failure could be observed is never silently recorded as a pass;
  see ``ClassOutcome.outcome``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

Source = Literal["real", "mock"]

FailureClass = Literal[
    "functional",
    "timing",
    "concurrency",
    "resource_soak",
    "peripheral_edge",
]
FAILURE_CLASSES: tuple[FailureClass, ...] = (
    "functional",
    "timing",
    "concurrency",
    "resource_soak",
    "peripheral_edge",
)

Severity = Literal["info", "warning", "error"]

# pass / fail are observed outcomes. The two censored variants keep a truncated run
# from masquerading as a clean pass: "survived" means the required window was reached
# without failure (a genuine pass for survival criteria); "unknown" means the run was
# cut short before the criterion could be decided and the label is therefore missing.
ClassOutcomeStatus = Literal["pass", "fail", "censored_survived", "censored_unknown"]


# Computed fields (pass rates, censoring, overall reliability) are emitted on
# serialization; ignoring unknown keys on load lets a record round-trip through JSONL
# and recompute them from the stored primitives rather than rejecting them.
class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=False)


class StaticFinding(_Strict):
    tool: Literal["cppcheck", "clang-tidy"]
    severity: Severity
    rule: str
    file: str
    line: int
    message: str


class EmulationTiming(_Strict):
    """Timing as seen under emulation. Present only when the emulation backend can
    model time at all; the ``null`` backend leaves it absent so its blindness to
    timing is recorded as missing data rather than a fabricated zero."""

    deadline_miss_rate: float = Field(ge=0.0, le=1.0)
    jitter_us: float = Field(ge=0.0)
    backend: str


class CheapOracles(_Strict):
    unit_tests_total: int = Field(ge=0)
    unit_tests_passed: int = Field(ge=0)
    static_findings: list[StaticFinding] = Field(default_factory=list)
    emulation_functional: bool
    emulation_backend: str
    emulation_timing: Optional[EmulationTiming] = None
    confidence_verbalized: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    confidence_logprob: Optional[float] = Field(default=None, le=0.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unit_test_pass_rate(self) -> float:
        if self.unit_tests_total == 0:
            return 0.0
        return self.unit_tests_passed / self.unit_tests_total


class ClassOutcome(_Strict):
    failure_class: FailureClass
    outcome: ClassOutcomeStatus
    measurements: dict[str, float] = Field(default_factory=dict)
    raw_artifact: Optional[str] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def censored(self) -> bool:
        return self.outcome in ("censored_survived", "censored_unknown")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reliable(self) -> Optional[bool]:
        """True/False for a decided run; None when censoring left the label unknown.
        A None here propagates to ``ProgramRecord.hardware_reliable`` and excludes the
        record from gap counts rather than being coerced to a pass."""
        if self.outcome == "pass" or self.outcome == "censored_survived":
            return True
        if self.outcome == "fail":
            return False
        return None


class GroundTruth(_Strict):
    outcomes: list[ClassOutcome] = Field(min_length=1)

    def by_class(self, failure_class: FailureClass) -> Optional[ClassOutcome]:
        for outcome in self.outcomes:
            if outcome.failure_class == failure_class:
                return outcome
        return None


class ProgramRecord(_Strict):
    record_id: str
    task_id: str
    failure_class: FailureClass
    task_family: str

    model_id: str
    api_model_string: str
    model_date: str
    open_weight: bool
    sample_index: int = Field(ge=0)

    prompt_hash: str
    code_hash: str
    harness_version: str
    board_id: str
    toolchain_versions: dict[str, str] = Field(default_factory=dict)
    source: Source

    oracles: CheapOracles
    ground_truth: GroundTruth

    oracle_predicted_reliable: bool
    difficulty: Optional[str] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hardware_reliable(self) -> Optional[bool]:
        """Overall real-hardware label across applicable classes. None when any
        applicable class is censored-unknown; disagreement between this and
        ``oracle_predicted_reliable`` is the gap the project measures."""
        labels = [o.reliable for o in self.ground_truth.outcomes]
        if any(label is None for label in labels):
            return None
        return all(labels)


class GenerationSample(_Strict):
    sample_id: str
    task_id: str
    model_id: str
    api_model_string: str
    model_date: str
    open_weight: bool
    sample_index: int = Field(ge=0)

    prompt_hash: str
    code_hash: str
    raw_output: str
    extracted_code: str

    confidence_verbalized: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    confidence_logprob: Optional[float] = Field(default=None, le=0.0)

    decoding: dict[str, float] = Field(default_factory=dict)
    request_timestamp: datetime
    source: Source


class RunManifest(_Strict):
    command: str
    created_at: datetime
    git_commit: Optional[str] = None
    config_hash: str
    source: Source
    seed: Optional[int] = None
    board_id: Optional[str] = None
    tool_versions: dict[str, str] = Field(default_factory=dict)
    model_registry: list[dict[str, object]] = Field(default_factory=list)
    extra: dict[str, object] = Field(default_factory=dict)
