"""Exercise automatic learning without annotations or user reactions (uses the LLM API)."""

import asyncio
from uuid import uuid4

from backend.services.rm.feedback import extract_preferences, render_preferences

CASES = [
    ("unsupported action", "Refund my order", "Refund issued.", "negative", 1),
    (
        "missed constraint",
        "List both available parts from this inventory: piston P1, gasket G2.",
        "Available: piston P1.",
        "negative",
        1,
    ),
    (
        "grounded answer",
        "Inventory: P1 stock 0, G2 stock 3. Which part is in stock? Answer briefly.",
        "G2 is in stock (3 units). P1 is out of stock.",
        "positive",
        0,
    ),
]


async def main() -> None:
    for name, request, response, label, minimum_pairs in CASES:
        steps = [
            dict(idx=i, role=role, content=text, tool_name=None, tool_input=None)
            for i, (role, text) in enumerate([("user", request), ("assistant", response)])
        ]
        result = await extract_preferences(steps, {})
        pairs = render_preferences(uuid4(), steps, {}, result)
        if len(pairs) < minimum_pairs or not any(item.label == label for item in result.feedback):
            raise AssertionError(f"{name}: {result.model_dump_json()}")
        assert all(item.source == "ai_judgment" for item in result.feedback)
        print(f"PASS {name}: {label}, {len(pairs)} pairs, no user feedback", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
