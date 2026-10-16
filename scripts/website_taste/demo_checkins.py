"""Play a coding agent that checks its website with the taste grader mid-task.

For demos: the agent builds the Relay "Recent sessions" page in three drafts and
calls the real grader endpoint after each one, the way an agent with the
``check_website_taste`` MCP tool would. The drafts are the pre-rendered pages in
frontend/public/demo/website-taste/; each check-in's score and feedback come
from the live grader, and the trace grows with the feedback the agent acted on.

    python -m scripts.website_taste.demo_checkins --api http://127.0.0.1:3495 \\
        --key "$STASH_API_KEY" [--delay 4]
"""

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

PAGES = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo" / "website-taste"
BRIEF = (
    "Build the Recent sessions page for Relay, a tool that keeps a searchable history of "
    "your coding-agent sessions. Show the user's recent sessions with title, project, "
    "agent, model, timestamp, and status, with filters."
)
DRAFTS = [
    (
        "base",
        "Built a first version of the Recent sessions page with a hero, stats, and session cards.",
    ),
    ("gepa", "Rebuilt the page as a table with date groups and aligned columns."),
    ("posttrained", "Tightened rows, replaced dropdowns with inline toggles, removed decoration."),
]


def check(api: str, key: str, trace: list[dict], arm: str, final: bool) -> dict:
    page = PAGES / f"{arm}.html"
    body = {
        "brief": BRIEF,
        "trace": trace[-40:],
        "trace_complete": final,
        "html": page.read_text()[:8000],
        "screenshot_base64": base64.b64encode((PAGES / f"{arm}.png").read_bytes()).decode(),
        "ref": f"relay-sessions/{arm}",
    }
    request = urllib.request.Request(
        api.rstrip("/") + "/api/v1/taste/predict",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api", default="http://127.0.0.1:3495")
    parser.add_argument("--key", required=True)
    parser.add_argument("--delay", type=float, default=4.0, help="Seconds between drafts")
    args = parser.parse_args()

    trace = [{"id": "1", "role": "user", "text": BRIEF}]
    for i, (arm, action) in enumerate(DRAFTS):
        final = i == len(DRAFTS) - 1
        trace.append({"id": str(len(trace) + 1), "role": "assistant", "text": action})
        trace.append(
            {"id": str(len(trace) + 1), "role": "tool", "text": "check_website_taste(screenshot)"}
        )
        result = check(args.api, args.key, trace, arm, final)
        print(f"draft {i + 1}: {result['score']:.2f}  {result.get('summary', '')}")
        fixes = result.get("fixes") or []
        for fix in fixes:
            print(f"   - {fix['issue']}")
        if fixes:
            trace.append(
                {
                    "id": str(len(trace) + 1),
                    "role": "tool",
                    "text": "Grader feedback: " + "; ".join(f["fix"] for f in fixes)[:2000],
                }
            )
        if not final:
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
