"""Static-analysis oracle: cppcheck and clang-tidy parsed into structured findings.

Only error-severity findings feed the optimistic oracle rule. Warning-severity ones
are retained in the record because they carry partial signal about the hidden hazard
that the predictor can learn from even though the rule ignores them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..config import RunConfig
from ..mock import LatentDraw
from ..schemas import Severity, StaticFinding

_CPPCHECK_SEVERITY: dict[str, Severity] = {
    "error": "error",
    "warning": "warning",
    "portability": "warning",
    "performance": "warning",
    "style": "info",
    "information": "info",
}


def run_static_analysis(
    cfg: RunConfig,
    source: str,
    source_file: Optional[Path],
    latent: Optional[LatentDraw],
) -> list[StaticFinding]:
    if source == "mock":
        assert latent is not None
        return [
            StaticFinding(tool=tool, severity=sev, rule=rule, file="generated.cpp", line=1 + i, message=msg)
            for i, (tool, sev, rule, msg) in enumerate(latent.findings)
        ]
    assert source_file is not None
    return _run_cppcheck(source_file) + _run_clang_tidy(source_file)


def _run_cppcheck(source_file: Path) -> list[StaticFinding]:
    if shutil.which("cppcheck") is None:
        raise RuntimeError("cppcheck not on PATH; required for the static-analysis oracle")
    template = "{file}\x01{line}\x01{severity}\x01{id}\x01{message}"
    proc = subprocess.run(
        ["cppcheck", "--enable=all", "--inline-suppr", f"--template={template}", str(source_file)],
        capture_output=True,
        text=True,
    )
    findings: list[StaticFinding] = []
    for line in proc.stderr.splitlines():
        parts = line.split("\x01")
        if len(parts) != 5:
            continue
        file, line_no, severity, rule, message = parts
        findings.append(
            StaticFinding(
                tool="cppcheck",
                severity=_CPPCHECK_SEVERITY.get(severity, "info"),
                rule=rule,
                file=file,
                line=int(line_no) if line_no.isdigit() else 0,
                message=message,
            )
        )
    return findings


def _run_clang_tidy(source_file: Path) -> list[StaticFinding]:
    if shutil.which("clang-tidy") is None:
        raise RuntimeError("clang-tidy not on PATH; required for the static-analysis oracle")
    proc = subprocess.run(
        ["clang-tidy", "--export-fixes=-", str(source_file), "--"],
        capture_output=True,
        text=True,
    )
    try:
        doc = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        doc = {}
    findings: list[StaticFinding] = []
    for diag in doc.get("Diagnostics", []):
        message = diag.get("DiagnosticMessage", {})
        rule = diag.get("DiagnosticName", "clang-tidy")
        severity: Severity = "error" if rule.startswith("clang-analyzer") else "warning"
        findings.append(
            StaticFinding(
                tool="clang-tidy",
                severity=severity,
                rule=rule,
                file=str(source_file),
                line=int(message.get("FileOffset", 0)),
                message=message.get("Message", ""),
            )
        )
    return findings
