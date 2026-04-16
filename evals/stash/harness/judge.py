"""
LLM-judged rubric scoring.

Reads the rubric, the starting prompt, the git diff, and the final assistant
message. Asks Opus to grade each criterion 0.0-1.0 with evidence. Returns
structured JSON.

For reliability, we run the judge 3x at temperature 0 and majority-vote the
`pass` field; scores are averaged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from anthropic import Anthropic

JUDGE_MODEL = os.environ.get("STASH_EVAL_JUDGE_MODEL", "claude-opus-4-7")
JUDGE_VOTES = int(os.environ.get("STASH_EVAL_JUDGE_VOTES", "3"))


JUDGE_SYSTEM = """You are grading a coding-agent's attempt at a software task. You will see:

- The task prompt the agent received.
- A rubric with weighted criteria.
- The agent's git diff (what it changed).
- The agent's final message.

Score each criterion 0.0–1.0 with concrete evidence from the diff. Then compute
an overall weighted score and a pass/fail.

Output strict JSON only, no markdown fences, matching the schema in the rubric."""


def build_user_prompt(
    starting_prompt: str,
    rubric: str,
    diff: str,
    final_message: str,
    check_results: list[dict],
) -> str:
    return f"""## Starting prompt
{starting_prompt}

## Rubric
{rubric}

## Deterministic check results
{json.dumps(check_results, indent=2)}

## Agent git diff
```diff
{diff}
```

## Agent final message
{final_message}

Grade now. Return JSON only.
"""


def judge_once(
    starting_prompt: str,
    rubric: str,
    diff: str,
    final_message: str,
    check_results: list[dict],
) -> dict[str, Any]:
    client = Anthropic()
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=4000,
        system=JUDGE_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": build_user_prompt(
                    starting_prompt, rubric, diff, final_message, check_results
                ),
            }
        ],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"Could not find JSON object in judge output:\n{text[:500]}")
    return json.loads(text[start : end + 1])


def judge(
    starting_prompt: str,
    rubric: str,
    diff: str,
    final_message: str,
    check_results: list[dict],
    votes: int = JUDGE_VOTES,
) -> dict[str, Any]:
    """Run the judge `votes` times; average scores, majority-vote on pass."""
    if any(not c.get("pass") for c in check_results):
        return {
            "overall_score": 0.0,
            "pass": False,
            "reason": "deterministic_check_failed",
            "check_results": check_results,
            "votes": [],
        }

    runs = [judge_once(starting_prompt, rubric, diff, final_message, check_results) for _ in range(votes)]
    passes = sum(1 for r in runs if r.get("pass"))
    avg_score = sum(r.get("overall_score", 0.0) for r in runs) / len(runs)
    return {
        "overall_score": avg_score,
        "pass": passes > votes / 2,
        "check_results": check_results,
        "votes": runs,
    }


def main() -> None:
    """Convenience: judge a trial dir from the command line."""
    import sys

    if len(sys.argv) != 3:
        print("usage: judge.py <trial_dir> <task_dir>", file=sys.stderr)
        sys.exit(2)
    trial = Path(sys.argv[1])
    task = Path(sys.argv[2])
    starting_prompt = (task / "starting_prompt.md").read_text()
    rubric = (task / "rubric.md").read_text()
    diff = (trial / "patch.diff").read_text()
    final_message = (trial / "final_message.txt").read_text() if (trial / "final_message.txt").exists() else ""
    check_results = json.loads((trial / "checks.json").read_text())
    result = judge(starting_prompt, rubric, diff, final_message, check_results)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
