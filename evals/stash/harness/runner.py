"""
Run one trial of the eval.

Per trial:
1. Make a git worktree at task.repo.base_sha under /tmp.
2. Isolate CLAUDE_CONFIG_DIR to a fresh temp dir.
3. For Arm B: create a stash workspace, seed events, point plugin at it.
4. For Arm A: strip `stash` from PATH; no plugin.
5. Call claude_agent_sdk.query() with the starting prompt.
6. Persist every message to transcript.jsonl with timestamps.
7. git diff base_sha..HEAD -> patch.diff.
8. Run deterministic checks.
9. Save metrics.json.

Usage:
    python -m harness.runner --task tasks/t1_browser_auth --arm a --trial 0
    python -m harness.runner --task tasks/t1_browser_auth --arm b --trial 0

Does NOT call the judge — that's a separate step so you can re-judge without
re-running trials.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from claude_agent_sdk import ClaudeAgentOptions, query

from . import metrics as metrics_mod
from . import seed_workspace

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "plugins" / "claude-plugin"


def load_task(task_dir: Path) -> dict:
    with open(task_dir / "task.yaml") as f:
        return yaml.safe_load(f)


def make_worktree(source_repo: str, base_sha: str, dest: Path) -> None:
    """Create a git worktree at the given SHA."""
    subprocess.run(
        ["git", "-C", source_repo, "worktree", "add", "--detach", str(dest), base_sha],
        check=True,
        capture_output=True,
    )


def remove_worktree(source_repo: str, dest: Path) -> None:
    subprocess.run(
        ["git", "-C", source_repo, "worktree", "remove", "--force", str(dest)],
        capture_output=True,
    )


def strip_stash_from_path(env: dict[str, str]) -> dict[str, str]:
    """Return a copy of env with `stash` binary's directory removed from PATH."""
    stash_bin = shutil.which("stash")
    if not stash_bin:
        return env
    stash_dir = str(Path(stash_bin).parent)
    path = env.get("PATH", "")
    env = dict(env)
    env["PATH"] = ":".join(p for p in path.split(":") if p != stash_dir)
    return env


NESTED_SENTINELS = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
)


def clear_nested_sentinels() -> None:
    """Remove Claude Code nested-session markers from os.environ.

    The SDK merges os.environ into the subprocess env, so setting these in
    options.env alone is not enough — they'd still leak through. Unsetting
    in our own process only affects this Python process and its children."""
    for key in NESTED_SENTINELS:
        os.environ.pop(key, None)


def build_options(arm: str, worktree: Path, task: dict, workspace_id: str | None) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions for the trial."""
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(worktree.parent / f"claude-config-{arm}")
    os.makedirs(env["CLAUDE_CONFIG_DIR"], exist_ok=True)

    plugins: list[dict] = []
    system_prompt = None

    if arm == "a":
        env = strip_stash_from_path(env)
        env.pop("STASH_CONFIG_DIR", None)
        env.pop("STASH_API_KEY", None)
    elif arm == "b":
        plugins = [{"type": "local", "path": str(PLUGIN_DIR)}]
        # Tell the agent a workspace with prior-session history exists.
        system_prompt = (
            "A prior Claude Code session in this workspace already explored related "
            "design decisions. Their findings are stored in the stash workspace "
            f"'{workspace_id}'. Consider using `stash history search` or "
            "`stash history query` to retrieve their findings before exploring the "
            "codebase from scratch.\n"
        )

    return ClaudeAgentOptions(
        cwd=str(worktree),
        model=os.environ.get("STASH_EVAL_AGENT_MODEL", "claude-sonnet-4-6"),
        permission_mode="bypassPermissions",
        max_turns=task.get("budgets", {}).get("max_turns", 80),
        env=env,
        plugins=plugins,
        system_prompt=system_prompt,
        setting_sources=[],
    )


BLOCK_TYPE_MAP = {
    "ToolUseBlock": "tool_use",
    "ToolResultBlock": "tool_result",
    "TextBlock": "text",
    "ThinkingBlock": "thinking",
}


def to_jsonable(obj: Any) -> Any:
    """Recursively convert SDK dataclass / pydantic / block objects to plain JSON types."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump())
    if hasattr(obj, "__dict__"):
        data = {k: to_jsonable(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
        cls_name = type(obj).__name__
        tag = BLOCK_TYPE_MAP.get(cls_name, cls_name.lower().replace("block", "").replace("message", ""))
        data.setdefault("type", tag)
        return data
    return repr(obj)


def message_to_dict(m: Any) -> dict:
    """Coerce an SDK message object into a plain dict for the transcript."""
    result = to_jsonable(m)
    if not isinstance(result, dict):
        return {"repr": repr(m)}
    return result


async def run_agent(
    prompt: str, options: ClaudeAgentOptions, transcript_path: Path
) -> tuple[list[dict], str]:
    """Stream messages from the SDK and write to transcript.jsonl. Return (messages, final_text)."""
    messages: list[dict] = []
    final_text = ""
    with open(transcript_path, "w") as fout:
        async for m in query(prompt=prompt, options=options):
            m_dict = message_to_dict(m)
            m_dict["sdk_type"] = type(m).__name__.replace("Message", "").lower()
            m_dict["_recorded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            messages.append(m_dict)
            fout.write(json.dumps(m_dict, default=str) + "\n")
            fout.flush()
            if m_dict["sdk_type"] == "assistant":
                for block in m_dict.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        final_text = block.get("text", final_text)
    return messages, final_text


def git_diff(worktree: Path, base_sha: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(worktree), "diff", base_sha],
        capture_output=True,
        text=True,
    )
    return r.stdout


def run_trial(task_dir: Path, arm: str, trial: int, run_id: str) -> dict:
    clear_nested_sentinels()
    task = load_task(task_dir)
    starting_prompt = (task_dir / task["starting_prompt_file"]).read_text().strip()
    seed_events_path = task_dir / task["seed_events_file"]

    trial_root = EVAL_ROOT / "runs" / run_id / f"arm_{arm}" / f"trial_{trial}"
    trial_root.mkdir(parents=True, exist_ok=True)

    worktree_dir = Path(tempfile.mkdtemp(prefix=f"stash-eval-{task['id']}-{arm}-{trial}-"))
    worktree_dir.rmdir()  # worktree add needs path not to exist
    make_worktree(task["repo"]["source_repo"], task["repo"]["base_sha"], worktree_dir)
    # Remove CLAUDE.md from the worktree — it references ~/.claude session history
    # which would give Arm A a back-door to the same kind of context stash provides.
    # Commit the removal so the agent's diff is measured against the cleaned base.
    claude_md = worktree_dir / "CLAUDE.md"
    trial_base_sha = task["repo"]["base_sha"]
    if claude_md.exists():
        claude_md.unlink()
        subprocess.run(
            ["git", "-C", str(worktree_dir), "add", "-A"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(worktree_dir), "-c", "user.email=eval@stash", "-c", "user.name=eval",
             "commit", "-m", "eval: strip CLAUDE.md from trial worktree"],
            check=True, capture_output=True,
        )
        trial_base_sha = subprocess.run(
            ["git", "-C", str(worktree_dir), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    print(f"[{arm}/{trial}] worktree: {worktree_dir}  trial_base={trial_base_sha[:10]}", file=sys.stderr)

    workspace_id: str | None = None
    if arm == "b":
        if not seed_events_path.exists():
            raise RuntimeError(f"arm b requires {seed_events_path}")
        workspace_name = f"eval-{task['id']}-{run_id}-{trial}"
        workspace_id = seed_workspace.seed(workspace_name, str(seed_events_path), dict(os.environ))
        print(f"[{arm}/{trial}] seeded workspace: {workspace_id}", file=sys.stderr)
        (trial_root / "workspace_id.txt").write_text(workspace_id)

    options = build_options(arm, worktree_dir, task, workspace_id)
    transcript_path = trial_root / "transcript.jsonl"

    start_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        _messages, final_text = asyncio.run(run_agent(starting_prompt, options, transcript_path))
    finally:
        end_ts = dt.datetime.now(dt.timezone.utc).isoformat()

    diff = git_diff(worktree_dir, trial_base_sha)
    (trial_root / "patch.diff").write_text(diff)
    (trial_root / "final_message.txt").write_text(final_text or "")

    check_results = metrics_mod.run_checks(task.get("checks", []), worktree_dir, diff)
    (trial_root / "checks.json").write_text(json.dumps(check_results, indent=2))

    metrics = metrics_mod.compute_metrics(transcript_path, task.get("session_a_touched_paths", []))
    metrics["arm"] = arm
    metrics["trial"] = trial
    metrics["run_id"] = run_id
    metrics["task_id"] = task["id"]
    metrics["workspace_id"] = workspace_id
    metrics["start_ts"] = start_ts
    metrics["end_ts"] = end_ts
    (trial_root / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    remove_worktree(task["repo"]["source_repo"], worktree_dir)
    print(f"[{arm}/{trial}] done. trial_root: {trial_root}", file=sys.stderr)
    return metrics


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--arm", required=True, choices=["a", "b"])
    p.add_argument("--trial", type=int, default=0)
    p.add_argument("--run-id", default=None)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    task_dir = Path(args.task).resolve()
    metrics = run_trial(task_dir, args.arm, args.trial, run_id)
    print(json.dumps(metrics, indent=2, default=str))


if __name__ == "__main__":
    main()
