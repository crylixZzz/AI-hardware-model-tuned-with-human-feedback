"""On-device functional test run.

This is the ground-truth counterpart to the cheap unit-test oracle: the same test
cases, executed on real silicon rather than on host or under emulation. For the
functional failure class the pass fraction here is the label.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..config import RunConfig
from ..mock import Injection, LatentDraw

_PIO_SUMMARY = re.compile(r"(\d+)\s+test cases?:\s+(\d+)\s+succeeded")


@dataclass(frozen=True)
class FunctionalMeasurement:
    tests_total: int
    tests_passed: int

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total if self.tests_total else 0.0


class FunctionalRunner(ABC):
    backend_name: str

    @abstractmethod
    def run(self) -> FunctionalMeasurement: ...


class MockFunctionalRunner(FunctionalRunner):
    backend_name = "mock"

    def __init__(self, latent: Optional[LatentDraw], injection: Optional[Injection]) -> None:
        self._latent = latent
        self._injection = injection

    def run(self) -> FunctionalMeasurement:
        inj = self._injection
        total = 12
        if inj is not None and inj.clean:
            return FunctionalMeasurement(total, total)
        if inj is not None and inj.device_pass_rate is not None:
            return FunctionalMeasurement(total, int(round(inj.device_pass_rate * total)))
        assert self._latent is not None
        return FunctionalMeasurement(total, int(round(self._latent.device_pass_rate * total)))


class PlatformIOFunctionalRunner(FunctionalRunner):
    backend_name = "platformio"

    def __init__(self, env: str) -> None:
        self._env = env

    def run(self) -> FunctionalMeasurement:
        if shutil.which("pio") is None:
            raise RuntimeError("PlatformIO ('pio') not on PATH; required to run on-device tests")
        proc = subprocess.run(
            ["pio", "test", "-e", self._env],
            capture_output=True,
            text=True,
        )
        match = _PIO_SUMMARY.search(proc.stdout)
        if match is None:
            raise RuntimeError("could not parse PlatformIO test summary from device run")
        total, passed = int(match.group(1)), int(match.group(2))
        return FunctionalMeasurement(total, passed)


def make_functional_runner(
    cfg: RunConfig,
    source: str,
    latent: Optional[LatentDraw] = None,
    injection: Optional[Injection] = None,
) -> FunctionalRunner:
    if source == "mock":
        return MockFunctionalRunner(latent=latent, injection=injection)
    return PlatformIOFunctionalRunner(env=cfg.board.id)
