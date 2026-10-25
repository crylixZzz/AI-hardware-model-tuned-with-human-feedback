"""Emulation oracle behind a swappable backend.

The emulation and hardware harnesses compile the identical generated source, so any
divergence between this oracle and the ground truth is a property of emulation
fidelity, not of two different programs. The ``null`` backend models nothing about
time and so leaves ``emulation_timing`` absent rather than reporting a fabricated zero.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import RunConfig
from ..mock import LatentDraw
from ..schemas import EmulationTiming


@dataclass(frozen=True)
class EmulationResult:
    functional: bool
    timing: Optional[EmulationTiming]
    backend: str


class EmulationBackend(ABC):
    name: str

    @abstractmethod
    def run(self, emu_env: str, project_dir: Optional[Path]) -> EmulationResult: ...


class MockEmulation(EmulationBackend):
    name = "mock"

    def __init__(self, latent: LatentDraw, measures_timing: bool) -> None:
        self._latent = latent
        self._measures_timing = measures_timing

    def run(self, emu_env: str, project_dir: Optional[Path]) -> EmulationResult:
        functional = self._latent.device_pass_rate >= 0.9
        timing = None
        if self._measures_timing:
            timing = EmulationTiming(
                deadline_miss_rate=self._latent.deadline_miss_rate_emulated,
                jitter_us=self._latent.jitter_us_emulated,
                backend=self.name,
            )
        return EmulationResult(functional=functional, timing=timing, backend=self.name)


class NullEmulation(EmulationBackend):
    """Functional-only: runs the program to completion under an instruction-accurate
    emulator with no timing model. Use when a cycle-accurate backend is unavailable."""

    name = "null"

    def run(self, emu_env: str, project_dir: Optional[Path]) -> EmulationResult:
        functional = _run_functional_emulation(emu_env, project_dir)
        return EmulationResult(functional=functional, timing=None, backend=self.name)


class QemuEmulation(EmulationBackend):
    name = "qemu"

    def run(self, emu_env: str, project_dir: Optional[Path]) -> EmulationResult:
        functional = _run_functional_emulation(emu_env, project_dir)
        # HARDWARE-TODO: wire QEMU's cycle counter / gpio trace to the harness deadline
        # markers to populate EmulationTiming. Until that trace is parsed, timing stays
        # absent rather than guessed, matching the null backend's honesty.
        return EmulationResult(functional=functional, timing=None, backend=self.name)


def _run_functional_emulation(emu_env: str, project_dir: Optional[Path]) -> bool:
    import shutil
    import subprocess

    if shutil.which("pio") is None:
        raise RuntimeError("PlatformIO ('pio') not on PATH; required to run the emulation harness")
    proc = subprocess.run(
        ["pio", "test", "-e", emu_env],
        cwd=str(project_dir) if project_dir else None,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def make_emulation_backend(cfg: RunConfig, source: str, latent: Optional[LatentDraw]) -> EmulationBackend:
    if source == "mock":
        assert latent is not None
        return MockEmulation(latent, measures_timing=cfg.emulation_backend in ("qemu", "mock"))
    if cfg.emulation_backend == "qemu":
        return QemuEmulation()
    if cfg.emulation_backend == "null":
        return NullEmulation()
    raise ValueError(f"unknown real emulation backend: {cfg.emulation_backend!r}")
