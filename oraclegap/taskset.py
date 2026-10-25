"""Task registry loader.

Tasks live under ``tasks/<id>/`` with a natural-language ``spec.md``, matched
emulation and hardware harnesses, and golden solutions. ``tasks/registry.yaml`` is
the index this reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict

from .schemas import FailureClass


class TaskMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    failure_class: FailureClass
    family: str
    difficulty: str
    deadline_us: Optional[float] = None  # timing tasks only
    harness_version: str = "1.0.0"
    summary: str

    def spec_path(self, repo_root: Path) -> Path:
        return repo_root / "tasks" / self.id / "spec.md"

    def golden_manifest_path(self, repo_root: Path) -> Path:
        return repo_root / "tasks" / self.id / "golden" / "manifest.yaml"


def load_tasks(repo_root: str | Path) -> list[TaskMeta]:
    repo_root = Path(repo_root)
    doc = yaml.safe_load((repo_root / "tasks" / "registry.yaml").read_text())
    return [TaskMeta(**entry) for entry in doc["tasks"]]


def load_task(repo_root: str | Path, task_id: str) -> TaskMeta:
    for task in load_tasks(repo_root):
        if task.id == task_id:
            return task
    raise KeyError(f"task not in registry: {task_id!r}")
