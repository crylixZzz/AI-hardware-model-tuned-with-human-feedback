"""Render the gap, calibration, and predictor analyses to JSON, Markdown tables, and
(when matplotlib is available) figures. Matplotlib is an optional convenience, not a
stack dependency; its absence degrades to tables only.
"""

from __future__ import annotations

import json
from pathlib import Path


def write_report(report_dir: Path, gap: dict, evaluation: dict, calibration: dict) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(
        json.dumps({"gap": gap, "evaluation": evaluation, "calibration": calibration}, indent=2, default=str)
    )
    md = _markdown(gap, evaluation, calibration)
    md_path = report_dir / "report.md"
    md_path.write_text(md)
    _figures(report_dir, gap, calibration)
    return md_path


def _fmt(x: float) -> str:
    return "n/a" if x != x else f"{x:.3f}"


def _markdown(gap: dict, evaluation: dict, calibration: dict) -> str:
    lines: list[str] = ["# Oracle Gap report", ""]

    lines += ["## Oracle-vs-hardware gap by failure class", ""]
    lines += ["| class | n | hw fail | over-pred rate [CI] | false reassurance | McNemar p (Holm) | sig |",
              "|---|--:|--:|---|--:|--:|:--:|"]
    for fc, row in gap["per_class"].items():
        op = row["over_prediction_rate"]
        mc = row["mcnemar"]
        lines.append(
            f"| {fc} | {row['n_usable']} | {row['n_hardware_failures']} | "
            f"{_fmt(op['point'])} [{_fmt(op['low'])}, {_fmt(op['high'])}] | "
            f"{_fmt(row['false_reassurance_rate'])} | {_fmt(mc.get('pvalue_holm', float('nan')))} | "
            f"{'yes' if mc.get('significant') else 'no'} |"
        )
    lines.append(f"\nCensored records excluded from the gap: {gap['n_censored_excluded']} of {gap['n_total']}.\n")

    lines += ["## Predictor vs best single cheap oracle", ""]
    for split, block in evaluation["splits"].items():
        best = block["best_single_oracle"]
        lines += [f"### {split}-split (best single oracle: `{best}`)", "",
                  "| model | AUROC [CI] | AUPRC [CI] | vs best: ΔAUROC [CI] | DeLong p | vs conf: ΔAUROC [CI] |",
                  "|---|---|---|---|--:|---|"]
        for kind, pr in block["predictors"].items():
            au, ap = pr["auroc_ci"], pr["auprc_ci"]
            vb, vc = pr["vs_best_oracle"], pr["vs_confidence"]
            lines.append(
                f"| {kind} | {_fmt(pr['auroc'])} [{_fmt(au['low'])}, {_fmt(au['high'])}] | "
                f"{_fmt(pr['auprc'])} [{_fmt(ap['low'])}, {_fmt(ap['high'])}] | "
                f"{_fmt(vb['auroc_diff_ci']['point'])} [{_fmt(vb['auroc_diff_ci']['low'])}, {_fmt(vb['auroc_diff_ci']['high'])}] | "
                f"{_fmt(vb['delong']['pvalue'])} | "
                f"{_fmt(vc['auroc_diff_ci']['point'])} [{_fmt(vc['auroc_diff_ci']['low'])}, {_fmt(vc['auroc_diff_ci']['high'])}] |"
            )
        bo = block["oracles"][best]
        lines.append(f"\nBest single oracle `{best}`: AUROC {_fmt(bo['auroc'])}, AUPRC {_fmt(bo['auprc'])}.\n")

    lines += ["## Confidence calibration vs hardware", ""]
    if calibration.get("n"):
        lines += [
            f"- n = {calibration['n']}",
            f"- Brier = {_fmt(calibration['brier'])}",
            f"- ECE = {_fmt(calibration['ece'])}",
            f"- mean confidence {_fmt(calibration['mean_confidence'])} vs observed reliability {_fmt(calibration['mean_reliable'])} "
            f"(overconfidence {_fmt(calibration['overconfidence'])})",
        ]
    else:
        lines.append("- no records with both confidence and a decided hardware label")
    return "\n".join(lines) + "\n"


def _figures(report_dir: Path, gap: dict, calibration: dict) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig_dir = report_dir / "figures"
    fig_dir.mkdir(exist_ok=True)

    classes = list(gap["per_class"])
    rates = [gap["per_class"][c]["over_prediction_rate"]["point"] for c in classes]
    lows = [rates[i] - gap["per_class"][c]["over_prediction_rate"]["low"] for i, c in enumerate(classes)]
    highs = [gap["per_class"][c]["over_prediction_rate"]["high"] - rates[i] for i, c in enumerate(classes)]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(classes, rates, yerr=[lows, highs], capsize=4, color="#b2182b")
    ax.set_ylabel("over-prediction rate")
    ax.set_title("Oracle over-prediction by failure class")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(fig_dir / "gap_by_class.png", dpi=120)
    plt.close(fig)

    if calibration.get("bins"):
        conf = [b["mean_confidence"] for b in calibration["bins"]]
        obs = [b["observed_reliable"] for b in calibration["bins"]]
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.plot([0, 1], [0, 1], "--", color="gray")
        ax.plot(conf, obs, "o-", color="#2166ac")
        ax.set_xlabel("stated confidence")
        ax.set_ylabel("observed reliability")
        ax.set_title(f"Reliability diagram (ECE {calibration['ece']:.3f})")
        fig.tight_layout()
        fig.savefig(fig_dir / "calibration.png", dpi=120)
        plt.close(fig)
