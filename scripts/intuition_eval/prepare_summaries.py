"""Fetch OpenAI summarize_from_feedback comparisons (validation split) via the HF datasets server.

Writes data/summaries_raw.jsonl (one comparison per line). Stdlib only, idempotent.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

ROWS = "https://datasets-server.huggingface.co/rows?dataset=openai/summarize_from_feedback&config=comparisons&split=validation&offset={offset}&length=100"
OUT = Path(__file__).parent / "data" / "summaries_raw.jsonl"


def fetch(offset: int) -> dict:
    for attempt in range(5):
        try:
            with urllib.request.urlopen(ROWS.format(offset=offset), timeout=60) as r:
                return json.load(r)
        except Exception:  # transient HF rate limits
            time.sleep(2 * (attempt + 1))
    raise SystemExit(f"failed at offset {offset}")


def main(limit: int) -> None:
    if OUT.exists():
        print("exists", OUT)
        return
    first = fetch(0)
    total = min(first["num_rows_total"], limit)
    rows = [r["row"] for r in first["rows"]]
    for offset in range(100, total, 100):
        rows.extend(r["row"] for r in fetch(offset)["rows"])
    OUT.write_text("".join(json.dumps(r) + "\n" for r in rows[:total]))
    print("wrote", len(rows[:total]), "of", first["num_rows_total"])


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20000)
