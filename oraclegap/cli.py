"""Command-line entrypoints.

Every command resolves one config, runs one stage, and writes a run manifest (config
hash, tool/model versions, git commit, UTC timestamp) so a result traces back to the
exact inputs that produced it. ``--real`` selects the real execution path; without it
every stage runs in mock mode.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import structlog
import typer

from . import analysis, pipeline
from .config import RunConfig, build_manifest, load_config, write_manifest
from .data.store import DatasetStore
from .schemas import Source
from .validation.self_test import run_self_validation

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(20))
log = structlog.get_logger("oraclegap")

app = typer.Typer(add_completion=False, help="Oracle Gap measurement framework")

_ConfigOpt = typer.Option("config/default.yaml", "--config", help="run config YAML")
_RootOpt = typer.Option(".", "--repo-root", help="repository root")
_RealOpt = typer.Option(False, "--real", help="use the real execution path instead of mock")


def _load(config: str, repo_root: str) -> RunConfig:
    return load_config(Path(repo_root) / config if not Path(config).is_absolute() else Path(config), repo_root)


def _source(real: bool) -> Source:
    return "real" if real else "mock"


def _manifest(command: str, cfg: RunConfig, source: Source, extra: Optional[dict] = None) -> None:
    write_manifest(build_manifest(command, cfg, source, extra=extra), cfg)


def _frame(cfg: RunConfig, source: Source):
    records = DatasetStore(cfg.repo_root / cfg.paths.dataset / source, source).read_records()
    return analysis.records_to_frame(records)


@app.command()
def generate(config: str = _ConfigOpt, repo_root: str = _RootOpt, real: bool = _RealOpt) -> None:
    cfg, source = _load(config, repo_root), _source(real)
    n = pipeline.run_generation(cfg, source)
    _manifest("generate", cfg, source, {"samples": n})
    typer.echo(f"generated {n} samples (source={source})")


@app.command("run-oracles")
def run_oracles(config: str = _ConfigOpt, repo_root: str = _RootOpt, real: bool = _RealOpt) -> None:
    cfg, source = _load(config, repo_root), _source(real)
    n = pipeline.run_oracles(cfg, source)
    _manifest("run-oracles", cfg, source, {"samples": n})
    typer.echo(f"ran oracles over {n} samples (source={source})")


@app.command("run-hardware")
def run_hardware(config: str = _ConfigOpt, repo_root: str = _RootOpt, real: bool = _RealOpt) -> None:
    cfg, source = _load(config, repo_root), _source(real)
    if real:
        log.info("hardware.real", board=cfg.board.id, timing_backend=cfg.timing_backend)
    n = pipeline.run_hardware(cfg, source)
    _manifest("run-hardware", cfg, source, {"samples": n})
    typer.echo(f"measured ground truth for {n} samples (source={source})")


@app.command("self-validate")
def self_validate(config: str = _ConfigOpt, repo_root: str = _RootOpt, real: bool = _RealOpt) -> None:
    cfg, source = _load(config, repo_root), _source(real)
    report = run_self_validation(cfg, source, artifact_dir=cfg.repo_root / cfg.paths.artifacts / source / "selftest")
    _manifest("self-validate", cfg, source, {"ok": report.ok, "cases": len(report.results)})
    for r in report.results:
        marker = "ok" if r.passed else "MISS"
        typer.echo(f"[{marker}] {r.task_id}/{r.name}: expected {r.expected}, got {r.actual}")
    if not report.ok:
        typer.echo(f"self-validation FAILED: {len(report.failures())} case(s) mismatched", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"self-validation passed: {len(report.results)} cases (source={source})")


@app.command("build-dataset")
def build_dataset(config: str = _ConfigOpt, repo_root: str = _RootOpt, real: bool = _RealOpt) -> None:
    cfg, source = _load(config, repo_root), _source(real)
    parquet = pipeline.build_dataset(cfg, source)
    _manifest("build-dataset", cfg, source, {"parquet": str(parquet)})
    typer.echo(f"dataset written: {parquet}")


@app.command()
def train(
    config: str = _ConfigOpt,
    repo_root: str = _RootOpt,
    real: bool = _RealOpt,
    split: str = typer.Option("family", "--split", help="family (headline) or random"),
) -> None:
    cfg, source = _load(config, repo_root), _source(real)
    frame = _frame(cfg, source)
    evaluation = analysis.evaluate(frame, cfg.thresholds)
    block = evaluation["splits"][split]
    typer.echo(f"{split}-split, best single oracle = {block['best_single_oracle']}")
    for kind, pr in block["predictors"].items():
        vb = pr["vs_best_oracle"]["auroc_diff_ci"]
        typer.echo(f"  {kind}: AUROC {pr['auroc']:.3f}  AUPRC {pr['auprc']:.3f}  ΔAUROC vs best {vb['point']:+.3f} [{vb['low']:.3f}, {vb['high']:.3f}]")
    out = cfg.repo_root / cfg.paths.runs / f"evaluation_{source}.json"
    out.write_text(json.dumps(evaluation, indent=2, default=str))
    _manifest("train", cfg, source, {"split": split, "evaluation": str(out)})


@app.command()
def analyze(config: str = _ConfigOpt, repo_root: str = _RootOpt, real: bool = _RealOpt) -> None:
    cfg, source = _load(config, repo_root), _source(real)
    frame = _frame(cfg, source)
    gap = analysis.gap_analysis(frame, cfg.thresholds)
    evaluation = analysis.evaluate(frame, cfg.thresholds)
    calibration = analysis.reliability_calibration(frame)
    report_dir = cfg.repo_root / cfg.paths.runs / f"report_{source}"
    md = analysis.write_report(report_dir, gap, evaluation, calibration)
    _manifest("analyze", cfg, source, {"report": str(md)})
    typer.echo(f"report written: {md}")


if __name__ == "__main__":
    app()
