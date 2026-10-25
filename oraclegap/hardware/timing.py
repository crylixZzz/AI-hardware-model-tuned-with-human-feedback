"""Timing ground-truth capture.

The device-under-test's own clock is never the timing reference (see LIMITATIONS):
these backends time deadlines from an independent instrument. Three are provided --
a sigrok-driven logic analyzer, a second microcontroller used as a counter, and the
seeded mock -- behind one interface so the rest of the pipeline is backend-agnostic.
"""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..config import RunConfig
from ..mock import Injection, LatentDraw


@dataclass(frozen=True)
class TimingMeasurement:
    deadline_miss_rate: float
    jitter_us: float
    samples: int
    truncated: bool  # capture ended before the planned window; outcome is unknown


class TimingCapture(ABC):
    backend_name: str

    @abstractmethod
    def capture(self, duration_s: float, deadline_us: float) -> TimingMeasurement: ...


class MockTimingCapture(TimingCapture):
    backend_name = "mock"

    def __init__(self, latent: Optional[LatentDraw], injection: Optional[Injection]) -> None:
        self._latent = latent
        self._injection = injection

    def capture(self, duration_s: float, deadline_us: float) -> TimingMeasurement:
        inj = self._injection
        if inj is not None and not inj.clean and (inj.jitter_us is not None or inj.deadline_miss_rate is not None):
            return TimingMeasurement(
                deadline_miss_rate=inj.deadline_miss_rate or 0.0,
                jitter_us=inj.jitter_us or 0.0,
                samples=int(duration_s * 1000),
                truncated=False,
            )
        if inj is not None and inj.clean:
            return TimingMeasurement(deadline_miss_rate=0.0, jitter_us=5.0, samples=int(duration_s * 1000), truncated=False)
        assert self._latent is not None
        return TimingMeasurement(
            deadline_miss_rate=self._latent.deadline_miss_rate,
            jitter_us=self._latent.jitter_us,
            samples=int(duration_s * 1000),
            truncated=False,
        )


class SigrokTimingCapture(TimingCapture):
    backend_name = "sigrok"

    def __init__(self, wiring: dict[str, str], tool_version: str) -> None:
        self._wiring = wiring
        self._tool_version = tool_version

    def capture(self, duration_s: float, deadline_us: float) -> TimingMeasurement:
        if shutil.which("sigrok-cli") is None:
            raise RuntimeError("sigrok-cli not on PATH; required for the 'sigrok' timing backend")
        channel = self._wiring.get("deadline_gpio_channel")
        if channel is None:
            # HARDWARE-TODO: set 'deadline_gpio_channel' to the fx2 logic-analyzer channel
            # wired to the GPIO the task harness toggles on each deadline event, and
            # 'trigger' to its edge spec. These are physical-wiring facts; there is no
            # correct default and guessing one would silently corrupt every timing label.
            raise RuntimeError("sigrok wiring incomplete: 'deadline_gpio_channel' unset (HARDWARE-TODO)")
        samples_hz = 1_000_000
        proc = subprocess.run(
            [
                "sigrok-cli",
                "--driver", "fx2lafw",
                "--channels", channel,
                "--config", f"samplerate={samples_hz}",
                "--samples", str(int(duration_s * samples_hz)),
                "--output-format", "csv",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return _parse_edge_csv(proc.stdout, deadline_us, samples_hz)


class CounterMcuTimingCapture(TimingCapture):
    backend_name = "counter-mcu"

    def __init__(self, wiring: dict[str, str]) -> None:
        self._wiring = wiring

    def capture(self, duration_s: float, deadline_us: float) -> TimingMeasurement:
        port = self._wiring.get("counter_serial_port")
        if port is None:
            # HARDWARE-TODO: set 'counter_serial_port' to the serial device of the
            # second MCU running the timestamping firmware (firmware/counter_mcu/), and
            # confirm its capture pin is wired to the DUT's deadline GPIO.
            raise RuntimeError("counter-mcu wiring incomplete: 'counter_serial_port' unset (HARDWARE-TODO)")
        raise RuntimeError(
            "counter-mcu capture requires the counter firmware session; see RUNBOOK (HARDWARE-TODO)"
        )


def _parse_edge_csv(csv_text: str, deadline_us: float, samples_hz: int) -> TimingMeasurement:
    intervals_us: list[float] = []
    last_edge: Optional[int] = None
    for line in csv_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            sample_idx, level = (int(x) for x in line.split(",")[:2])
        except ValueError:
            continue
        if level == 1:
            if last_edge is not None:
                intervals_us.append((sample_idx - last_edge) * 1_000_000 / samples_hz)
            last_edge = sample_idx
    if not intervals_us:
        return TimingMeasurement(0.0, 0.0, 0, truncated=True)
    misses = sum(1 for iv in intervals_us if iv > deadline_us)
    nominal = sum(intervals_us) / len(intervals_us)
    jitter = max(abs(iv - nominal) for iv in intervals_us)
    return TimingMeasurement(
        deadline_miss_rate=misses / len(intervals_us),
        jitter_us=jitter,
        samples=len(intervals_us),
        truncated=False,
    )


def make_timing_capture(
    cfg: RunConfig,
    source: str,
    latent: Optional[LatentDraw] = None,
    injection: Optional[Injection] = None,
    wiring: Optional[dict[str, str]] = None,
) -> TimingCapture:
    if source == "mock":
        return MockTimingCapture(latent=latent, injection=injection)
    wiring = wiring or {}
    if cfg.timing_backend == "sigrok":
        return SigrokTimingCapture(wiring, cfg.tool_versions.get("sigrok-cli", "unknown"))
    if cfg.timing_backend == "counter-mcu":
        return CounterMcuTimingCapture(wiring)
    raise ValueError(f"unknown real timing backend: {cfg.timing_backend!r}")
