"""Assemble the cheap-oracle block for one generated sample and apply the oracle rule.

All four oracles are gathered here so a single latent draw (in mock mode) feeds them
consistently, and so the optimistic ``oracle_predicted_reliable`` verdict is computed
in exactly one place from the pre-registered rule.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import OracleRule, RunConfig
from ..mock import LatentDraw, draw_latent
from ..schemas import CheapOracles, GenerationSample, Source
from ..taskset import TaskMeta
from .emulation import make_emulation_backend
from .static_analysis import run_static_analysis
from .unit_tests import run_unit_tests


def _emu_env(cfg: RunConfig) -> str:
    return f"{cfg.board.id}_emu"


def _latent_for(cfg: RunConfig, task: TaskMeta, sample: GenerationSample) -> LatentDraw:
    return draw_latent(
        seed=cfg.seed,
        task_id=task.id,
        model_id=sample.model_id,
        sample_index=sample.sample_index,
        failure_class=task.failure_class,
        difficulty=task.difficulty,
        emulation_measures_timing=cfg.emulation_backend in ("qemu", "mock"),
    )


def collect_oracles(
    cfg: RunConfig,
    source: Source,
    task: TaskMeta,
    sample: GenerationSample,
    project_dir: Optional[Path] = None,
    source_file: Optional[Path] = None,
) -> CheapOracles:
    latent = _latent_for(cfg, task, sample) if source == "mock" else None

    unit = run_unit_tests(cfg, source, _emu_env(cfg), project_dir, latent)
    findings = run_static_analysis(cfg, source, source_file, latent)
    emulation = make_emulation_backend(cfg, source, latent).run(_emu_env(cfg), project_dir)

    return CheapOracles(
        unit_tests_total=unit.total,
        unit_tests_passed=unit.passed,
        static_findings=findings,
        emulation_functional=emulation.functional,
        emulation_backend=emulation.backend,
        emulation_timing=emulation.timing,
        confidence_verbalized=sample.confidence_verbalized,
        confidence_logprob=sample.confidence_logprob,
    )


def oracle_predicted_reliable(oracles: CheapOracles, rule: OracleRule) -> bool:
    if oracles.unit_test_pass_rate < rule.min_pass_rate:
        return False
    forbidden = set(rule.forbidden_severities)
    if any(f.severity in forbidden for f in oracles.static_findings):
        return False
    if rule.require_emulation_functional and not oracles.emulation_functional:
        return False
    if oracles.emulation_timing is not None and oracles.emulation_timing.jitter_us > rule.max_emulation_jitter_us:
        return False
    return True
