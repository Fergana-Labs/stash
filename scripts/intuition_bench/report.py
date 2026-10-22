"""Write RESULTS.md from results/raw/*.json (see run.py)."""

from __future__ import annotations

import json
from pathlib import Path

from .tasks import all_tasks

HERE = Path(__file__).parent
RAW = HERE / "results" / "raw"
SIGNALS = {
    "Jev zero-shot": "Jev + references",
    "Embedding probe": "probe only",
    "Rubric criteria": "criteria only",
}


def pct(v) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def cell(r: dict | None) -> str:
    if not r:
        return "—"
    if r.get("status") != "ok":
        return "error"
    lo, hi = r["ci"]
    return f"{pct(r['accuracy'])} <sub>[{pct(lo)}–{pct(hi)}]</sub>"


def main() -> None:
    results = {}
    for path in RAW.glob("*.json"):
        r = json.loads(path.read_text())
        results[(r["task"], r["arm"])] = r
    tasks = [t for t in all_tasks() if any(k[0] == t.name for k in results)]
    budgets = sorted({int(a.split("@")[1]) for _, a in results if a.startswith("intuition@")})
    arms = ["jev_zero_shot", "claude@0"] + [
        f"{p}@{n}" for n in budgets for p in ("claude", "intuition")
    ]
    head = {"jev_zero_shot": "Jev zero-shot", "claude@0": "Claude, no examples"}
    for n in budgets:
        head[f"claude@{n}"] = f"Claude + {n} examples"
        head[f"intuition@{n}"] = f"**Intuition, {n} labels**"

    lines = [
        "# Intuition benchmark",
        "",
        "Accuracy on a fixed held-out test set per task, with 95% Wilson intervals. Every arm sees the "
        "same test items; labeled examples come from a separate pool.",
        "",
        "| Task | Kind | Test n | " + " | ".join(head[a] for a in arms) + " |",
        "|---|---|---:|" + "---:|" * len(arms),
    ]
    for t in tasks:
        n = next(
            (
                results[(t.name, a)]["n"]
                for a in arms
                if (t.name, a) in results and results[(t.name, a)].get("n")
            ),
            "",
        )
        lines.append(
            f"| {t.title} | {t.kind} | {n} | "
            + " | ".join(cell(results.get((t.name, a))) for a in arms)
            + " |"
        )

    lines += [
        "",
        "## Calibration (expected calibration error, lower is better)",
        "",
        "| Task | " + " | ".join(head[a] for a in arms) + " |",
        "|---|" + "---:|" * len(arms),
    ]
    for t in tasks:
        row = []
        for a in arms:
            r = results.get((t.name, a))
            row.append(
                "—"
                if not r or r.get("status") != "ok" or r.get("ece") is None
                else f"{r['ece']:.3f}"
            )
        lines.append(f"| {t.title} | " + " | ".join(row) + " |")

    lines += ["", "## Inside the intuition: each signal alone on the same test set", ""]
    for n in budgets:
        lines += [
            f"**{n} labels**",
            "",
            "| Task | " + " | ".join(SIGNALS.values()) + " | combined | criteria from |",
            "|---|" + "---:|" * (len(SIGNALS) + 1) + "---|",
        ]
        for t in tasks:
            r = results.get((t.name, f"intuition@{n}"))
            if not r or r.get("status") != "ok":
                continue
            board = {e["name"]: e["accuracy"] for e in r["leaderboard"]}
            lines.append(
                f"| {t.title} | "
                + " | ".join(pct(board.get(k)) for k in SIGNALS)
                + f" | {pct(r['accuracy'])} | {r['criteria_mode']} |"
            )
        lines.append("")

    multi = [t for t in tasks if t.output_type == "multi"]
    if multi:
        lines += ["## Multi-label: per-emotion accuracy", ""]
        for t in multi:
            for a in arms:
                r = results.get((t.name, a))
                if r and r.get("per_issue"):
                    lines.append(
                        f"- {head[a]}: "
                        + ", ".join(f"{k} {pct(v)}" for k, v in r["per_issue"].items())
                    )
        lines.append("")

    errors = [
        f"- {t}/{a}: {r['error']}"
        for (t, a), r in sorted(results.items())
        if r.get("status") != "ok"
    ]
    if errors:
        lines += ["## Errors", "", *errors, ""]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
