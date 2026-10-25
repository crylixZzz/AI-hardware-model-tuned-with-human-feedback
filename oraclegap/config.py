"""Typed configuration, loaded from YAML and never hardcoded elsewhere.

Analysis thresholds in particular are pre-registered in ``config/thresholds.yaml``
and reach the rest of the code only through :class:`Thresholds`. No module may
inline a pass-rate cutoff, jitter bound, or significance level.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict

from .schemas import RunManifest, Severity, Source


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelSpec(_Strict):
    id: str
    provider: str
    api_model_string: str
    date: str
    open_weight: bool


class BoardConfig(_Strict):
    id: str
    fallback: str


class Paths(_Strict):
    dataset: str
    artifacts: str
    runs: str


class FunctionalThresholds(_Strict):
    min_pass_rate: float


class TimingThresholds(_Strict):
    max_deadline_miss_rate: float
    max_jitter_us: float


class ConcurrencyThresholds(_Strict):
    max_race_events: int


class SoakThresholds(_Strict):
    required_hours: float


class PeripheralThresholds(_Strict):
    max_edge_failures: int


class OracleRule(_Strict):
    """Defines ``oracle_predicted_reliable``: the optimistic pre-deployment verdict
    whose disagreement with hardware is the gap."""

    min_pass_rate: float
    forbidden_severities: list[Severity]
    require_emulation_functional: bool
    max_emulation_jitter_us: float


class AnalysisThresholds(_Strict):
    alpha: float
    bootstrap_iterations: int
    bootstrap_seed: int


class Thresholds(_Strict):
    functional: FunctionalThresholds
    timing: TimingThresholds
    concurrency: ConcurrencyThresholds
    resource_soak: SoakThresholds
    peripheral_edge: PeripheralThresholds
    oracle_rule: OracleRule
    analysis: AnalysisThresholds


class RunConfig(_Strict):
    board: BoardConfig
    k: int
    seed: int
    emulation_backend: str
    timing_backend: str
    paths: Paths
    tool_versions: dict[str, str]
    models: list[ModelSpec]
    thresholds: Thresholds
    repo_root: Path
    config_hash: str

    def open_weight_models(self) -> list[ModelSpec]:
        return [m for m in self.models if m.open_weight]


def _canonical_hash(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_config(config_path: str | Path, repo_root: str | Path) -> RunConfig:
    repo_root = Path(repo_root).resolve()
    raw = yaml.safe_load(Path(config_path).read_text())

    models_doc = yaml.safe_load((repo_root / raw["generation"]["models_registry"]).read_text())
    thresholds_doc = yaml.safe_load((repo_root / raw["thresholds_file"]).read_text())

    merged = {"run": raw, "models": models_doc, "thresholds": thresholds_doc}

    return RunConfig(
        board=BoardConfig(**raw["board"]),
        k=raw["generation"]["k"],
        seed=raw["generation"]["seed"],
        emulation_backend=raw["emulation"]["backend"],
        timing_backend=raw["timing_capture"]["backend"],
        paths=Paths(**raw["paths"]),
        tool_versions=raw["tool_versions"],
        models=[ModelSpec(**m) for m in models_doc["models"]],
        thresholds=Thresholds(**thresholds_doc),
        repo_root=repo_root,
        config_hash=_canonical_hash(merged),
    )


def git_commit(repo_root: str | Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out.stdout.strip() or None


def build_manifest(
    command: str,
    cfg: RunConfig,
    source: Source,
    seed: Optional[int] = None,
    extra: Optional[dict[str, object]] = None,
) -> RunManifest:
    return RunManifest(
        command=command,
        created_at=datetime.now(timezone.utc),
        git_commit=git_commit(cfg.repo_root),
        config_hash=cfg.config_hash,
        source=source,
        seed=seed if seed is not None else cfg.seed,
        board_id=cfg.board.id,
        tool_versions=cfg.tool_versions,
        model_registry=[m.model_dump() for m in cfg.models],
        extra=extra or {},
    )


def write_manifest(manifest: RunManifest, cfg: RunConfig) -> Path:
    runs_dir = cfg.repo_root / cfg.paths.runs
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = manifest.created_at.strftime("%Y%m%dT%H%M%S%fZ")
    path = runs_dir / f"{manifest.command}_{stamp}.json"
    path.write_text(manifest.model_dump_json(indent=2))
    return path
