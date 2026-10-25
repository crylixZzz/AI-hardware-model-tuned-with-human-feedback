"""Build and flash the generated program onto the board.

The emulation and hardware paths compile the identical generated source (that is the
whole point of the matched-harness requirement); this module is the hardware half of
that. In mock mode it is a no-op that reports success without touching a device.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class FlashResult:
    ok: bool
    source: str
    env: str
    image_path: Optional[str] = None
    detail: Optional[str] = None


def flash(source: str, env: str, project_dir: Path) -> FlashResult:
    if source == "mock":
        return FlashResult(ok=True, source="mock", env=env, detail="no-op mock flash")
    if shutil.which("pio") is None:
        raise RuntimeError("PlatformIO ('pio') not on PATH; required to build and flash")
    proc = subprocess.run(
        ["pio", "run", "-e", env, "-t", "upload"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return FlashResult(ok=False, source="real", env=env, detail=proc.stderr[-2000:])
    firmware = project_dir / ".pio" / "build" / env / "firmware.bin"
    return FlashResult(
        ok=True,
        source="real",
        env=env,
        image_path=str(firmware) if firmware.exists() else None,
    )
