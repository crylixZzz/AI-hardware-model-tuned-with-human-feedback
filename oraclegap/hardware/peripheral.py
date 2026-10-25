"""Peripheral boundary / electrical-edge probe.

Exercises the program across a fixed battery of protocol and electrical edge cases
(timing-marginal ACKs, bus contention, brown-out thresholds, min/max register values)
and counts how many are handled incorrectly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..config import RunConfig
from ..mock import Injection, LatentDraw


@dataclass(frozen=True)
class PeripheralMeasurement:
    edge_failures: int
    edge_total: int


class PeripheralProbe(ABC):
    backend_name: str

    @abstractmethod
    def probe(self) -> PeripheralMeasurement: ...


class MockPeripheralProbe(PeripheralProbe):
    backend_name = "mock"

    def __init__(self, latent: Optional[LatentDraw], injection: Optional[Injection]) -> None:
        self._latent = latent
        self._injection = injection

    def probe(self) -> PeripheralMeasurement:
        inj = self._injection
        if inj is not None and inj.clean:
            return PeripheralMeasurement(0, inj.edge_total)
        if inj is not None and inj.edge_failures is not None:
            return PeripheralMeasurement(inj.edge_failures, inj.edge_total)
        assert self._latent is not None
        return PeripheralMeasurement(self._latent.edge_failures, self._latent.edge_total)


class DevicePeripheralProbe(PeripheralProbe):
    backend_name = "device"

    def __init__(self, wiring: dict[str, str]) -> None:
        self._wiring = wiring

    def probe(self) -> PeripheralMeasurement:
        rig = self._wiring.get("edge_rig")
        if rig is None:
            # HARDWARE-TODO: name the connected edge-injection rig (programmable supply +
            # bus fault injector) and its channel map. Electrical edges cannot be mocked
            # into existence on real silicon; without the rig there is no measurement.
            raise RuntimeError("peripheral wiring incomplete: 'edge_rig' unset (HARDWARE-TODO)")
        raise RuntimeError(
            "device peripheral probe requires the edge-injection rig; see RUNBOOK (HARDWARE-TODO)"
        )


def make_peripheral_probe(
    cfg: RunConfig,
    source: str,
    latent: Optional[LatentDraw] = None,
    injection: Optional[Injection] = None,
    wiring: Optional[dict[str, str]] = None,
) -> PeripheralProbe:
    if source == "mock":
        return MockPeripheralProbe(latent=latent, injection=injection)
    return DevicePeripheralProbe(wiring or {})
