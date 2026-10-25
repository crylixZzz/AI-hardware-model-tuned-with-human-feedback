"""Seeded synthetic model behind every ``mock`` backend.

Mock mode is not decoration: it lets the whole pipeline run with no hardware and it
is the substrate the self-validation suite plants known failures into. For the
measurement to be meaningful the mock must be internally consistent -- a single
program's cheap-oracle observations and its hardware outcome have to be drawn from
one latent state, or the "gap" would be an artifact of two unrelated random draws.

The latent state separates two hazards, and that separation is the whole point:

- ``h_visible`` produces error-severity static findings and depresses functional
  tests. Cheap oracles catch it, so it creates little gap.
- ``h_hidden`` drives timing/concurrency/soak/peripheral failure on hardware while
  leaving functional tests green and producing only warning-severity findings. The
  oracle rule (which keys on error severity and pass rate) is blind to it. That
  blindness is the gap; recovering ``h_hidden`` from warnings + emulated timing +
  confidence + failure class is what a learned predictor can do and a single oracle
  cannot.

Everything is a deterministic function of ``(seed, task_id, model_id, sample_index)``,
so a run reproduces exactly and tests can assert on fixed numbers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .schemas import FailureClass

# How exposed each class is to non-functional, hardware-only failure. Functional code
# is nearly fully observable by cheap oracles; concurrency and soak are the opposite.
CLASS_HARDNESS: dict[FailureClass, float] = {
    "functional": 0.10,
    "timing": 0.80,
    "concurrency": 0.90,
    "resource_soak": 0.85,
    "peripheral_edge": 0.55,
}

DIFFICULTY_LEVEL: dict[str, float] = {"easy": 0.25, "medium": 0.50, "hard": 0.80}

# Single hazard level above which a program fails on hardware, shared by all classes.
# Keeping one global cut (rather than per-class) makes the hazard-to-failure mapping
# class-independent, which is what both lets the cheap proxies rank failures pooled and
# lets a predictor trained on some families carry over to a held-out family. Class
# hardness still shifts the hazard, so failure rates differ by class.
_FAIL_TAU = 0.44
_HAZARD_BASE = 0.10
_HAZARD_SCALE = 0.55
_HAZARD_STD = 0.16
_WARN_BASE = 1.0
_WARN_SLOPE = 3.5
_LOGPROB_SLOPE = 1.0
_LOGPROB_NOISE = 0.45
_SOAK_WINDOW_S = 4.0 * 3600.0

_ERROR_RULES = [
    ("cppcheck", "nullPointer", "Possible null pointer dereference"),
    ("cppcheck", "uninitvar", "Uninitialized variable used"),
    ("clang-tidy", "clang-analyzer-core.CallAndMessage", "Call to function with uninitialized argument"),
]
_WARNING_RULES = [
    ("clang-tidy", "concurrency-mt-unsafe", "Call is not thread-safe"),
    ("clang-tidy", "bugprone-volatile", "Shared variable accessed without volatile qualifier"),
    ("cppcheck", "unusedScopedObject", "Guard object constructed but not retained for full scope"),
    ("clang-tidy", "performance-no-automatic-move", "Copy where a move was possible in a hot path"),
]
_INFO_RULES = [
    ("cppcheck", "style", "Prefer const where the value is not mutated"),
    ("clang-tidy", "readability-magic-numbers", "Magic number; name the constant"),
]


def _rng(*parts: object) -> np.random.Generator:
    key = "|".join(str(p) for p in parts).encode()
    digest = hashlib.blake2b(key, digest_size=8).digest()
    return np.random.default_rng(int.from_bytes(digest, "big"))


def model_skill(model_id: str) -> float:
    """Deterministic latent competence in [0.5, 0.85]. Kept a pure function of the id
    so no model identity is hardcoded in the generative story."""
    digest = hashlib.blake2b(model_id.encode(), digest_size=4).digest()
    unit = int.from_bytes(digest, "big") / 0xFFFFFFFF
    return 0.5 + 0.35 * unit


def difficulty_level(name: Optional[str]) -> float:
    return DIFFICULTY_LEVEL.get(name or "medium", 0.5)


@dataclass(frozen=True)
class Injection:
    """A planted defect for self-validation. When passed to a mock backend it forces
    exact measurements, bypassing the random latent draw so the ground-truth layer's
    detection can be checked against a known answer."""

    clean: bool = False
    device_pass_rate: Optional[float] = None
    deadline_miss_rate: Optional[float] = None
    jitter_us: Optional[float] = None
    race_events: Optional[int] = None
    time_to_failure_s: Optional[float] = None
    observation_window_s: Optional[float] = None
    edge_failures: Optional[int] = None
    edge_total: int = 16


@dataclass(frozen=True)
class LatentDraw:
    q: float
    h_visible: float
    h_hidden: float

    device_pass_rate: float
    unit_tests_total: int
    unit_tests_passed: int

    jitter_us: float
    deadline_miss_rate: float
    jitter_us_emulated: float
    deadline_miss_rate_emulated: float

    race_events: int

    time_to_failure_s: float
    observation_window_s: float

    edge_failures: int
    edge_total: int

    findings: list[tuple[str, str, str, str]] = field(default_factory=list)
    confidence_verbalized: float = 0.0
    confidence_logprob: float = 0.0


def _findings(rng: np.random.Generator, h_visible: float, hazard: float, q: float) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for severity, pool, lam in (
        # Error findings track the visible (functional-bug) hazard, which the oracle rule
        # already keys on, so they add little gap. Warnings track the hidden hazard the
        # rule ignores -- one of the two noisy signals the predictor combines.
        ("error", _ERROR_RULES, 0.03 + 0.9 * h_visible),
        ("warning", _WARNING_RULES, _WARN_BASE + _WARN_SLOPE * hazard),
        ("info", _INFO_RULES, 0.8 + 1.5 * (1.0 - q)),
    ):
        for _ in range(int(rng.poisson(lam))):
            tool, rule, message = pool[int(rng.integers(len(pool)))]
            out.append((tool, severity, rule, message))
    return out


def draw_latent(
    seed: int,
    task_id: str,
    model_id: str,
    sample_index: int,
    failure_class: FailureClass,
    difficulty: Optional[str],
    emulation_measures_timing: bool,
) -> LatentDraw:
    rng = _rng(seed, task_id, model_id, sample_index)
    hardness = CLASS_HARDNESS[failure_class]
    skill = model_skill(model_id)
    diff = difficulty_level(difficulty)

    q = float(np.clip(skill - 0.18 * diff + rng.normal(0, 0.08), 0.05, 0.99))

    # One latent hazard drives hardware failure in every class; weaker code and harder
    # classes raise it. Failure is a per-class threshold on this single hazard, and the
    # two cheap proxies below are independent noisy views of this same value with the
    # same mapping in every class -- that shared mapping is what lets a predictor trained
    # on some families generalize to a family it never saw.
    hazard = float(np.clip(
        _HAZARD_BASE + _HAZARD_SCALE * (1.0 - q) * (0.60 + 0.50 * hardness) + rng.normal(0, _HAZARD_STD),
        0.0, 1.0,
    ))
    fails = hazard > _FAIL_TAU
    # A smaller, q-driven visible-bug hazard; it only populates error findings.
    h_visible = float(np.clip(0.3 * (1.0 - q) + rng.normal(0, 0.07), 0.0, 1.0))

    # Hardware manifestations are synthesized on the correct side of each class threshold
    # so the runner's threshold logic reproduces `fails`. These are ground truth, never
    # predictor features (the only timing feature, emulated jitter, is deliberately blind).
    if failure_class == "functional":
        device_pass_rate = float(rng.uniform(0.5, 0.88) if fails else rng.uniform(0.965, 1.0))
    else:
        # Functionally sound regardless of the non-functional hazard, so the cheap tests
        # pass and the oracle rule calls it reliable -- which is the gap.
        device_pass_rate = float(np.clip(0.99 - 0.08 * h_visible + rng.normal(0, 0.01), 0.3, 1.0))

    observed_pass_rate = float(np.clip(device_pass_rate + rng.normal(0, 0.015), 0.0, 1.0))
    unit_tests_total = 12
    unit_tests_passed = int(round(observed_pass_rate * unit_tests_total))

    if fails:
        jitter_us = float(rng.uniform(210.0, 950.0))
        deadline_miss_rate = float(rng.uniform(0.012, 0.09))
    else:
        jitter_us = float(rng.uniform(40.0, 185.0))
        deadline_miss_rate = float(rng.uniform(0.0, 0.008))

    # Emulated timing is blind: a heavy underestimate plus host-scheduling noise leaves it
    # barely tied to the real deadline behaviour, so it rarely crosses the bound a failing
    # program crosses on silicon.
    jitter_us_emulated = float(max(0.0, 70.0 + rng.normal(0, 45.0)))
    deadline_miss_rate_emulated = float(max(0.0, rng.normal(0.001, 0.002)))

    race_events = int(1 + rng.poisson(2.0)) if fails else 0

    if fails:
        time_to_failure_s = float(rng.uniform(300.0, _SOAK_WINDOW_S * 0.9))
    else:
        time_to_failure_s = float(rng.uniform(_SOAK_WINDOW_S * 1.2, _SOAK_WINDOW_S * 8.0))
    observation_window_s = _SOAK_WINDOW_S

    edge_total = 16
    edge_failures = int(1 + rng.binomial(6, 0.3)) if fails else 0

    findings = _findings(rng, h_visible, hazard, q)

    confidence_verbalized = float(np.clip(92.0 - 9.0 * (1.0 - q) - 12.0 * h_visible + rng.normal(0, 5.0), 1.0, 100.0))
    # Second independent view of the hazard: the decoder is less certain on hazardous
    # code. Its noise is independent of the warning count, so the two combine to a better
    # hazard estimate than either alone.
    confidence_logprob = float(-max(0.01, 0.2 + _LOGPROB_SLOPE * hazard + rng.normal(0, _LOGPROB_NOISE)))

    h_hidden = hazard
    if not emulation_measures_timing:
        jitter_us_emulated = 0.0
        deadline_miss_rate_emulated = 0.0

    return LatentDraw(
        q=q,
        h_visible=h_visible,
        h_hidden=h_hidden,
        device_pass_rate=device_pass_rate,
        unit_tests_total=unit_tests_total,
        unit_tests_passed=unit_tests_passed,
        jitter_us=jitter_us,
        deadline_miss_rate=deadline_miss_rate,
        jitter_us_emulated=jitter_us_emulated,
        deadline_miss_rate_emulated=deadline_miss_rate_emulated,
        race_events=race_events,
        time_to_failure_s=time_to_failure_s,
        observation_window_s=observation_window_s,
        edge_failures=edge_failures,
        edge_total=edge_total,
        findings=findings,
        confidence_verbalized=confidence_verbalized,
        confidence_logprob=confidence_logprob,
    )
