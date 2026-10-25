"""End-to-end stage functions behind the CLI.

Each stage reads the previous stage's ledger and writes its own, so generation,
cheap oracles, and hardware ground truth stay decoupled and independently rerunnable.
``build_dataset`` joins the three by ``sample_id`` into validated program records.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from .config import RunConfig
from .data.store import DatasetStore
from .generation.generate import generate_samples
from .groundtruth.runner import run_ground_truth
from .oracles.collect import collect_oracles, oracle_predicted_reliable
from .schemas import CheapOracles, GenerationSample, GroundTruth, ProgramRecord, Source
from .taskset import TaskMeta, load_tasks

log = structlog.get_logger(__name__)


def _dataset_root(cfg: RunConfig, source: Source) -> Path:
    return cfg.repo_root / cfg.paths.dataset / source


def _artifact_root(cfg: RunConfig, source: Source) -> Path:
    return cfg.repo_root / cfg.paths.artifacts / source


def _task_index(cfg: RunConfig) -> dict[str, TaskMeta]:
    return {t.id: t for t in load_tasks(cfg.repo_root)}


def run_generation(cfg: RunConfig, source: Source) -> int:
    store = DatasetStore(_dataset_root(cfg, source), source)
    samples = generate_samples(cfg, source, load_tasks(cfg.repo_root), cfg.models)
    return store.append_generation(samples)


def run_oracles(cfg: RunConfig, source: Source) -> int:
    store = DatasetStore(_dataset_root(cfg, source), source)
    tasks = _task_index(cfg)
    out = store.root / "oracles.jsonl"
    n = 0
    with out.open("w") as fh:
        for sample in store.read_generation():
            task = tasks[sample.task_id]
            oracles = collect_oracles(cfg, source, task, sample)
            predicted = oracle_predicted_reliable(oracles, cfg.thresholds.oracle_rule)
            fh.write(json.dumps({
                "sample_id": sample.sample_id,
                "oracles": oracles.model_dump(),
                "oracle_predicted_reliable": predicted,
            }) + "\n")
            n += 1
    log.info("oracles.done", samples=n, path=str(out))
    return n


def run_hardware(cfg: RunConfig, source: Source) -> int:
    store = DatasetStore(_dataset_root(cfg, source), source)
    tasks = _task_index(cfg)
    artifact_dir = _artifact_root(cfg, source)
    out = store.root / "groundtruth.jsonl"
    n = 0
    with out.open("w") as fh:
        for sample in store.read_generation():
            task = tasks[sample.task_id]
            ground_truth = run_ground_truth(
                cfg, source, task, sample.model_id, sample.sample_index,
                record_id=sample.sample_id, artifact_dir=artifact_dir,
            )
            fh.write(json.dumps({
                "sample_id": sample.sample_id,
                "record_id": sample.sample_id,
                "ground_truth": ground_truth.model_dump(),
            }) + "\n")
            n += 1
    log.info("hardware.done", samples=n, path=str(out))
    return n


def build_dataset(cfg: RunConfig, source: Source) -> Path:
    store = DatasetStore(_dataset_root(cfg, source), source)
    tasks = _task_index(cfg)

    samples = {s.sample_id: s for s in store.read_generation()}
    oracles = _load_keyed(store.root / "oracles.jsonl")
    ground = _load_keyed(store.root / "groundtruth.jsonl")

    missing = set(samples) - (set(oracles) & set(ground))
    if missing:
        raise RuntimeError(f"cannot build dataset: {len(missing)} samples lack oracle or hardware results")

    records: list[ProgramRecord] = []
    for sample_id, sample in samples.items():
        task = tasks[sample.task_id]
        oracle_block = CheapOracles.model_validate(oracles[sample_id]["oracles"])
        records.append(_assemble(cfg, source, task, sample, oracle_block,
                                 oracles[sample_id]["oracle_predicted_reliable"],
                                 GroundTruth.model_validate(ground[sample_id]["ground_truth"])))

    # Rebuild the records ledger from scratch so a re-run is idempotent rather than
    # appending duplicates onto the append-only file.
    store.records_path.unlink(missing_ok=True)
    store.append_records(records)
    return store.export_parquet()


def _assemble(
    cfg: RunConfig,
    source: Source,
    task: TaskMeta,
    sample: GenerationSample,
    oracles: CheapOracles,
    predicted: bool,
    ground_truth: GroundTruth,
) -> ProgramRecord:
    return ProgramRecord(
        record_id=sample.sample_id,
        task_id=task.id,
        failure_class=task.failure_class,
        task_family=task.family,
        model_id=sample.model_id,
        api_model_string=sample.api_model_string,
        model_date=sample.model_date,
        open_weight=sample.open_weight,
        sample_index=sample.sample_index,
        prompt_hash=sample.prompt_hash,
        code_hash=sample.code_hash,
        harness_version=task.harness_version,
        board_id=cfg.board.id,
        toolchain_versions=cfg.tool_versions,
        source=source,
        oracles=oracles,
        ground_truth=ground_truth,
        oracle_predicted_reliable=predicted,
        difficulty=task.difficulty,
    )


def _load_keyed(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {row["sample_id"]: row for row in rows}
