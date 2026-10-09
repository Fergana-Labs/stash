#!/usr/bin/env python3
"""Prepare a compact, text-only AgentRewardBench eval set for judge-model experiments.

Reads the V28 manifest (165 records) from the analytical_reward_compiler repo,
downloads each trajectory JSON into data/arb_raw/ (skipping files already present),
and writes data/agentrewardbench.jsonl with one record per line:
    {"key", "benchmark", "split", "label": 0|1, "goal", "text"}

The text contains the goal, per-step reasoning/action/error/url/page title, the agent's
final message, and a short excerpt of the final observation. Accessibility trees, DOM,
screenshots, LLM prompts, and all evaluator/reward fields (e.g. summary_info.cum_reward)
are excluded. Downloads are treated as untrusted data and only parsed as JSON.

Stdlib only; idempotent. Usage:
    .venv/bin/python scripts/intuition_eval/prepare_agentrewardbench.py [--manifest PATH] [--no-download]
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures as cf
import json
import os
import re
import statistics
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RAW_DIR = DATA_DIR / "arb_raw"
OUT_PATH = DATA_DIR / "agentrewardbench.jsonl"
DEFAULT_MANIFEST = Path(
    "/Users/samzliu/code/analytical_reward_compiler/research/rapid_llm_rl/results/"
    "AGENT_REWARDBENCH_TEXT_V28_MANIFEST.json"
)

MAX_TEXT = 18_000
REASONING_CAP = 400
ACTION_CAP = 600
ERROR_CAP = 400
URL_CAP = 300
FINAL_OBS_CAP = 1500
FINAL_MSG_CAP = 2000
HEAD_STEPS = 3
TAIL_STEPS = 8
MAX_BYTES = 10 * 1024 * 1024  # refuse anything absurdly large


def raw_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key.replace(":", "__"))
    return RAW_DIR / f"{safe}.json"


def download(record: dict) -> str | None:
    path = raw_path(record["key"])
    if path.exists():
        return None
    url = record["url"]
    if not url.startswith("https://huggingface.co/"):
        return f"refusing non-HF url: {url}"
    try:
        with urllib.request.urlopen(url, timeout=180) as resp:
            data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return "download exceeds size limit"
        json.loads(data)  # validate as JSON only
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return None
    except Exception as exc:  # noqa: BLE001
        return repr(exc)


def clip(text: str, cap: int) -> str:
    text = text.strip()
    if len(text) <= cap:
        return text
    return text[: cap - 3].rstrip() + "..."


def oneline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def page_title(step: dict) -> str:
    axtree = step.get("axtree") or ""
    m = re.match(r"\s*RootWebArea '((?:[^'\\]|\\.)*)'", axtree)
    return m.group(1) if m else ""


FINAL_FUNCS = ("send_msg_to_user", "report_infeasible")


def parse_final_message(action: str) -> tuple[str, str] | None:
    """Return (func, message) if action is send_msg_to_user/report_infeasible."""
    action = action.strip()
    for func in FINAL_FUNCS:
        if action.startswith(func + "("):
            arg = action[len(func) + 1 :]
            if arg.endswith(")"):
                arg = arg[:-1]
            try:
                val = ast.literal_eval(arg.strip())  # literal parsing only, never eval
                if isinstance(val, str):
                    return func, val
            except Exception:  # noqa: BLE001
                pass
            return func, arg.strip()
    return None


def format_step(i: int, step: dict) -> str:
    lines = [f"## Step {i + 1}"]
    url = step.get("url") or ""
    title = page_title(step)
    if url:
        lines.append(f"URL: {clip(url, URL_CAP)}")
    if title:
        lines.append(f"Page title: {clip(title, 200)}")
    reasoning = step.get("reasoning") or ""
    if reasoning.strip():
        lines.append(f"Thought: {clip(oneline(reasoning), REASONING_CAP)}")
    action = step.get("action") or ""
    lines.append(f"Action: {clip(action.strip(), ACTION_CAP)}" if action.strip() else "Action: (none)")
    return "\n".join(lines)


def build_text(traj: dict) -> tuple[str, str, bool]:
    goal = (traj.get("goal") or "").strip()
    steps = traj.get("steps") or []

    # The error from executing step i's action appears in step i+1's last_action_error.
    action_steps = []
    for i, step in enumerate(steps):
        if not (step.get("action") or "").strip():
            continue
        err = ""
        if i + 1 < len(steps):
            err = (steps[i + 1].get("last_action_error") or "").strip()
        block = format_step(len(action_steps), step)
        if err:
            block += f"\nError: {clip(oneline(err), ERROR_CAP)}"
        action_steps.append(block)

    # Final message to the user.
    final_msg = None
    for step in reversed(steps):
        act = (step.get("action") or "").strip()
        if act:
            final_msg = parse_final_message(act)
            if final_msg is None:
                last_action = act
            break
    else:
        last_action = None
    if final_msg:
        func, msg = final_msg
        label = "Agent reported task infeasible" if func == "report_infeasible" else "Agent's final message to user"
        final_section = f"# {label}\n{clip(msg, FINAL_MSG_CAP)}"
    else:
        final_section = (
            "# Agent's final message to user\n(none -- the agent did not send a final message; "
            f"last action: {clip(last_action or '(none)', ACTION_CAP)})"
        )

    # Final observation excerpt.
    final_obs_section = ""
    if steps:
        last = steps[-1]
        obs = (last.get("axtree_pruned") or last.get("axtree") or "").strip()
        header = ["# Final page state (excerpt of last observation)"]
        if last.get("url"):
            header.append(f"URL: {clip(last['url'], URL_CAP)}")
        title = page_title(last)
        if title:
            header.append(f"Page title: {clip(title, 200)}")
        if obs:
            obs = re.sub(r"\t", "  ", obs)
            header.append(clip(obs, FINAL_OBS_CAP))
        final_obs_section = "\n".join(header)

    goal_section = f"# User goal\n{goal}"

    def assemble(step_blocks: list[str]) -> str:
        parts = [goal_section, "# Agent trajectory\n" + ("\n\n".join(step_blocks) if step_blocks else "(no actions)")]
        parts.append(final_section)
        if final_obs_section:
            parts.append(final_obs_section)
        return "\n\n".join(parts)

    text = assemble(action_steps)
    truncated = False
    if len(text) > MAX_TEXT:
        truncated = True
        n = len(action_steps)
        if n > HEAD_STEPS + TAIL_STEPS:
            omitted = n - HEAD_STEPS - TAIL_STEPS
            blocks = action_steps[:HEAD_STEPS] + [f"[... {omitted} middle steps omitted ...]"] + action_steps[-TAIL_STEPS:]
            text = assemble(blocks)
        if len(text) > MAX_TEXT:  # last resort hard cut of trajectory middle
            tail = "\n\n" + final_section + ("\n\n" + final_obs_section if final_obs_section else "")
            head = text[: MAX_TEXT - len(tail) - 40]
            text = head + "\n[... truncated ...]" + tail
    return goal, text, truncated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    records = manifest["records"]
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    failures: dict[str, str] = {}
    if not args.no_download:
        with cf.ThreadPoolExecutor(args.workers) as ex:
            for rec, err in zip(records, ex.map(download, records)):
                if err:
                    failures[rec["key"]] = f"download: {err}"

    out_rows = []
    lengths = []
    n_trunc = 0
    for rec in records:
        if rec["key"] in failures:
            continue
        path = raw_path(rec["key"])
        if not path.exists():
            failures[rec["key"]] = "missing raw file"
            continue
        try:
            traj = json.loads(path.read_text())
            goal, text, truncated = build_text(traj)
        except Exception as exc:  # noqa: BLE001
            failures[rec["key"]] = f"parse: {exc!r}"
            continue
        n_trunc += truncated
        lengths.append(len(text))
        out_rows.append(
            {
                "key": rec["key"],
                "benchmark": rec["benchmark"],
                "split": rec["split"],
                "label": int(rec["label"]),
                "goal": goal,
                "text": text,
            }
        )

    tmp = OUT_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w") as fh:
        for row in out_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT_PATH)

    counts: dict[str, int] = {}
    for row in out_rows:
        k = f"{row['split']}_{row['label']}"
        counts[k] = counts.get(k, 0) + 1
    print(f"wrote {len(out_rows)} rows -> {OUT_PATH}")
    print("counts:", dict(sorted(counts.items())))
    if lengths:
        print(f"text chars: min={min(lengths)} median={int(statistics.median(lengths))} max={max(lengths)}")
    print(f"truncated: {n_trunc}")
    if failures:
        print("failures:")
        for k, v in failures.items():
            print(f"  {k}: {v}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
