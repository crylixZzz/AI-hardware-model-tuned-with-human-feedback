"""Unit-test oracle: pass@k from the emulation/host harness.

This is the cheapest and most trusted oracle, and for functional tasks it tracks
hardware well. The project's thesis is that for non-functional classes it stays green
while hardware fails -- which is why its result alone is never the verdict.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import RunConfig
from ..mock import LatentDraw

_PIO_SUMMARY = re.compile(r"(\d+)\s+test cases?:\s+(\d+)\s+succeeded")


@dataclass(frozen=True)
class UnitTestResult:
    total: int
    passed: int


def run_unit_tests(
    cfg: RunConfig,
    source: str,
    emu_env: str,
    project_dir: Optional[Path],
    latent: Optional[LatentDraw],
) -> UnitTestResult:
    if source == "mock":
        assert latent is not None
        return UnitTestResult(total=latent.unit_tests_total, passed=latent.unit_tests_passed)
    if shutil.which("pio") is None:
        raise RuntimeError("PlatformIO ('pio') not on PATH; required to run the emulation test harness")
    proc = subprocess.run(
        ["pio", "test", "-e", emu_env],
        cwd=str(project_dir) if project_dir else None,
        capture_output=True,
        text=True,
    )
    match = _PIO_SUMMARY.search(proc.stdout)
    if match is None:
        raise RuntimeError("could not parse PlatformIO test summary from emulation run")
    return UnitTestResult(total=int(match.group(1)), passed=int(match.group(2)))
