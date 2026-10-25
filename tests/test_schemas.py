import pytest

from oraclegap.schemas import (
    CheapOracles,
    ClassOutcome,
    GroundTruth,
    ProgramRecord,
)


def _record(outcome: str, source: str = "mock") -> ProgramRecord:
    return ProgramRecord(
        record_id="t:m:0",
        task_id="t",
        failure_class="resource_soak",
        task_family="fam",
        model_id="m",
        api_model_string="m-1",
        model_date="2025-01-01",
        open_weight=True,
        sample_index=0,
        prompt_hash="ph",
        code_hash="ch",
        harness_version="1.0.0",
        board_id="esp32",
        source=source,
        oracles=CheapOracles(
            unit_tests_total=12,
            unit_tests_passed=12,
            emulation_functional=True,
            emulation_backend="mock",
        ),
        ground_truth=GroundTruth(outcomes=[ClassOutcome(failure_class="resource_soak", outcome=outcome)]),
        oracle_predicted_reliable=True,
    )


def test_pass_rate_computed():
    oracles = CheapOracles(unit_tests_total=12, unit_tests_passed=9, emulation_functional=True, emulation_backend="mock")
    assert oracles.unit_test_pass_rate == pytest.approx(0.75)


def test_censored_unknown_is_not_a_pass():
    outcome = ClassOutcome(failure_class="resource_soak", outcome="censored_unknown")
    assert outcome.censored is True
    assert outcome.reliable is None  # never silently coerced to a pass


def test_censored_survived_is_reliable():
    outcome = ClassOutcome(failure_class="resource_soak", outcome="censored_survived")
    assert outcome.censored is True
    assert outcome.reliable is True


def test_hardware_reliable_none_when_label_unknown():
    assert _record("censored_unknown").hardware_reliable is None
    assert _record("fail").hardware_reliable is False
    assert _record("pass").hardware_reliable is True


def test_record_round_trips_through_json():
    record = _record("fail")
    restored = ProgramRecord.model_validate_json(record.model_dump_json())
    assert restored.hardware_reliable is False
    assert restored.oracles.unit_test_pass_rate == 1.0
