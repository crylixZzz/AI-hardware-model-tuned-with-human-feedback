"""Induced-load concurrency stressor.

Drives the program under a fixed interrupt/task-contention protocol and counts
data-corruption or lost-update events reported by the harness (via a CRC-guarded
shared structure). The pass criterion is zero events: races are not graded on a curve.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..config import RunConfig
from ..mock import Injection, LatentDraw


@dataclass(frozen=True)
class ConcurrencyMeasurement:
    race_events: int
    stress_duration_s: float


class ConcurrencyStressor(ABC):
    backend_name: str

    @abstractmethod
    def stress(self, duration_s: float) -> ConcurrencyMeasurement: ...


class MockConcurrencyStressor(ConcurrencyStressor):
    backend_name = "mock"

    def __init__(self, latent: Optional[LatentDraw], injection: Optional[Injection]) -> None:
        self._latent = latent
        self._injection = injection

    def stress(self, duration_s: float) -> ConcurrencyMeasurement:
        inj = self._injection
        if inj is not None and inj.clean:
            return ConcurrencyMeasurement(0, duration_s)
        if inj is not None and inj.race_events is not None:
            return ConcurrencyMeasurement(inj.race_events, duration_s)
        assert self._latent is not None
        return ConcurrencyMeasurement(self._latent.race_events, duration_s)


class DeviceConcurrencyStressor(ConcurrencyStressor):
    backend_name = "device"

    def __init__(self, wiring: dict[str, str]) -> None:
        self._wiring = wiring

    def stress(self, duration_s: float) -> ConcurrencyMeasurement:
        port = self._wiring.get("telemetry_serial_port")
        if port is None:
            # HARDWARE-TODO: set 'telemetry_serial_port'; the harness must report its
            # shared-structure CRC-mismatch count over that UART under the stress load.
            raise RuntimeError("concurrency wiring incomplete: 'telemetry_serial_port' unset (HARDWARE-TODO)")
        raise RuntimeError(
            "device concurrency stress requires a live board under the load generator; see RUNBOOK (HARDWARE-TODO)"
        )


def make_concurrency_stressor(
    cfg: RunConfig,
    source: str,
    latent: Optional[LatentDraw] = None,
    injection: Optional[Injection] = None,
    wiring: Optional[dict[str, str]] = None,
) -> ConcurrencyStressor:
    if source == "mock":
        return MockConcurrencyStressor(latent=latent, injection=injection)
    return DeviceConcurrencyStressor(wiring or {})
