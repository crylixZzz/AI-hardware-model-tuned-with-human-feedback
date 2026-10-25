"""Instrument self-validation.

The ground-truth layer is the measuring instrument for this whole project, so it must
prove it can catch failures it was told are present. Each task ships a clean reference
and planted-failure variants with known defects (``tasks/<id>/golden/manifest.yaml``).
This suite runs every variant through the exact threshold logic in
``groundtruth.runner`` and asserts the known defect is detected in its class and the
clean reference passes. If any planted failure is missed or any reference is flagged,
no measurement the instrument later produces is trustworthy, so the run fails loudly.

In mock mode the defect is supplied as an :class:`Injection` so detection is
deterministic. On real hardware (``source="real"``) the variant's source is flashed
and measured instead; that path requires the board (see RUNBOOK).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml

from ..config import RunConfig
from ..groundtruth.runner import run_ground_truth
from ..hardware.flash import flash
from ..mock import Injection
from ..schemas import Source
from ..taskset import TaskMeta, load_tasks

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SelfTestCase:
    task: TaskMeta
    name: str
    kind: str  # "reference" | "planted"
    expected_outcome: str
    defect: str
    source_file: str
    injection: Injection


@dataclass(frozen=True)
class CaseResult:
    task_id: str
    name: str
    kind: str
    expected: str
    actual: str
    passed: bool
    defect: str


@dataclass(frozen=True)
class SelfTestReport:
    ok: bool
    results: list[CaseResult]

    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]


def load_cases(repo_root: str | Path) -> list[SelfTestCase]:
    cases: list[SelfTestCase] = []
    for task in load_tasks(repo_root):
        manifest_path = task.golden_manifest_path(Path(repo_root))
        doc = yaml.safe_load(manifest_path.read_text())
        ref = doc["reference"]
        cases.append(_case(task, ref, "reference"))
        for variant in doc.get("planted", []):
            cases.append(_case(task, variant, "planted"))
    return cases


def _case(task: TaskMeta, entry: dict, kind: str) -> SelfTestCase:
    return SelfTestCase(
        task=task,
        name=entry["name"],
        kind=kind,
        expected_outcome=entry["expected_outcome"],
        defect=entry.get("defect", ""),
        source_file=entry["source"],
        injection=Injection(**entry.get("injection", {})),
    )


def run_self_validation(cfg: RunConfig, source: Source, artifact_dir: Path | None = None) -> SelfTestReport:
    results: list[CaseResult] = []
    for case in load_cases(cfg.repo_root):
        if source == "real":
            project_dir = cfg.repo_root / "tasks" / case.task.id
            # HARDWARE-TODO: the harness must build against golden/<source_file> for this
            # case (a one-line #include swap in harness_hw) before upload; wire that in
            # the PlatformIO env, then this flash+measure validates on real silicon.
            flash_result = flash(source="real", env=cfg.board.id, project_dir=project_dir)
            if not flash_result.ok:
                results.append(CaseResult(case.task.id, case.name, case.kind, case.expected_outcome, "flash_failed", False, case.defect))
                continue
            ground_truth = run_ground_truth(
                cfg, source, case.task, "selftest", 0, record_id=f"selftest:{case.task.id}:{case.name}", artifact_dir=artifact_dir,
            )
        else:
            ground_truth = run_ground_truth(
                cfg, source, case.task, "selftest", 0,
                record_id=f"selftest:{case.task.id}:{case.name}",
                injection=case.injection, artifact_dir=artifact_dir,
            )
        actual = ground_truth.outcomes[0].outcome
        results.append(
            CaseResult(
                task_id=case.task.id,
                name=case.name,
                kind=case.kind,
                expected=case.expected_outcome,
                actual=actual,
                passed=actual == case.expected_outcome,
                defect=case.defect,
            )
        )

    ok = all(r.passed for r in results)
    if not ok:
        for r in results:
            if not r.passed:
                log.error("self_validation.miss", task=r.task_id, case=r.name, expected=r.expected, actual=r.actual)
    return SelfTestReport(ok=ok, results=results)
