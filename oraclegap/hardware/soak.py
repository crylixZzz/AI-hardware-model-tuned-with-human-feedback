"""Resource-exhaustion soak monitor.

Watches a long-running deployment for watchdog resets, heap exhaustion, or stack
overflow. Outcomes are frequently right-censored -- the run is stopped at the
required window before any failure appears -- and that is represented honestly
rather than booked as a clean pass.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..config import RunConfig
from ..mock import Injection, LatentDraw


@dataclass(frozen=True)
class SoakMeasurement:
    observed_window_s: float
    time_to_failure_s: Optional[float]  # None => survived to observed_window_s
    failure_kind: Optional[str]
    aborted: bool  # run ended for an unrelated reason; label is unknown, not a pass


class SoakMonitor(ABC):
    backend_name: str

    @abstractmethod
    def monitor(self, max_duration_s: float) -> SoakMeasurement: ...


class MockSoakMonitor(SoakMonitor):
    backend_name = "mock"

    def __init__(self, latent: Optional[LatentDraw], injection: Optional[Injection]) -> None:
        self._latent = latent
        self._injection = injection

    def monitor(self, max_duration_s: float) -> SoakMeasurement:
        inj = self._injection
        if inj is not None and inj.clean:
            return SoakMeasurement(max_duration_s, None, None, aborted=False)
        if inj is not None and inj.time_to_failure_s is not None:
            window = inj.observation_window_s or max_duration_s
            ttf = inj.time_to_failure_s
            if ttf >= window:
                return SoakMeasurement(window, None, None, aborted=False)
            return SoakMeasurement(window, ttf, "heap_exhaustion", aborted=False)
        assert self._latent is not None
        window = min(max_duration_s, self._latent.observation_window_s)
        ttf = self._latent.time_to_failure_s
        if ttf >= window:
            return SoakMeasurement(window, None, None, aborted=False)
        return SoakMeasurement(window, ttf, "heap_exhaustion", aborted=False)


class SerialSoakMonitor(SoakMonitor):
    """Real monitor: reads periodic heap/stack telemetry and reset cause over the
    DUT's debug UART and flags the first exhaustion event."""

    backend_name = "serial"

    def __init__(self, wiring: dict[str, str]) -> None:
        self._wiring = wiring

    def monitor(self, max_duration_s: float) -> SoakMeasurement:
        port = self._wiring.get("telemetry_serial_port")
        if port is None:
            # HARDWARE-TODO: set 'telemetry_serial_port' to the DUT debug-UART device and
            # ensure the task harness emits the agreed heap/stack telemetry line each second.
            raise RuntimeError("soak wiring incomplete: 'telemetry_serial_port' unset (HARDWARE-TODO)")
        raise RuntimeError(
            "serial soak monitor runs for hours against a live board; see RUNBOOK (HARDWARE-TODO)"
        )


def make_soak_monitor(
    cfg: RunConfig,
    source: str,
    latent: Optional[LatentDraw] = None,
    injection: Optional[Injection] = None,
    wiring: Optional[dict[str, str]] = None,
) -> SoakMonitor:
    if source == "mock":
        return MockSoakMonitor(latent=latent, injection=injection)
    return SerialSoakMonitor(wiring or {})
