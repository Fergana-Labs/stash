"""Run synthetic feedback cases against the configured classifier (uses the LLM API).

uv run --env-file .env python -m backend.scripts.eval_rm_feedback
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from backend.services.rm.feedback import extract_preferences, render_preferences


async def main() -> None:
    cases = json.loads(
        (Path(__file__).resolve().parents[1] / "tests/fixtures/rm_feedback_cases.json").read_text()
    )
    semaphore = asyncio.Semaphore(3)

    async def evaluate(case: dict) -> tuple[bool, int]:
        steps = [
            {"idx": i, "role": role, "content": content, "tool_name": None, "tool_input": None}
            for i, (role, content) in enumerate(case["messages"])
        ]
        evidence = {
            f"step:{s['idx']}": {"kind": "user", "step_index": s["idx"], "text": s["content"]}
            for s in steps
            if s["role"] == "user"
        }
        async with semaphore:
            result = await extract_preferences(steps, evidence)
        result.feedback = [item for item in result.feedback if item.source == "user_feedback"]
        try:
            pairs = render_preferences(uuid4(), steps, evidence, result)
        except ValueError as error:
            raise ValueError(f"{case['name']}: {result.model_dump_json()}") from error
        labels = {str(item.step_index): item.label for item in result.feedback}
        passed = labels in case["labels"] and len(pairs) <= case["pairs"]
        print(
            json.dumps(
                {"case": case["name"], "passed": passed, "labels": labels, "pairs": len(pairs)}
            )
        )
        if not passed:
            print(result.model_dump_json())
        return passed, len(pairs)

    results = await asyncio.gather(*(evaluate(case) for case in cases))
    passed = sum(ok for ok, _ in results)
    pair_count = sum(count for _, count in results)
    print(f"{passed}/{len(cases)} synthetic cases passed; {pair_count} accepted comparisons.")
    print("This is not a production accuracy estimate.")
    if passed != len(cases) or pair_count < 2:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
