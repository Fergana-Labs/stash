"""Check an HTML page against your Stash taste grader, for coding agents.

Renders the page (JavaScript off), sends the screenshot, HTML and brief to the
grader endpoint, and prints the score, whether it is approved, and what to fix.
Each call is saved as an agent check-in on the eval page.

    python -m scripts.website_taste.check_page PAGE.html --brief "What the page is for"

Needs STASH_API_KEY; STASH_URL defaults to the local backend.
"""

import argparse
import base64
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from backend.services.taste import screenshot_page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("page", type=Path)
    parser.add_argument("--brief", required=True, help="What the page should be")
    parser.add_argument("--note", default="", help="What you changed since the last check")
    parser.add_argument("--final", action="store_true", help="This is the finished page")
    args = parser.parse_args()

    key = os.environ.get("STASH_API_KEY")
    if not key:
        sys.exit("Set STASH_API_KEY.")
    html = args.page.read_text()
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "page.png"
        screenshot_page(png, html=html)
        shot = base64.b64encode(png.read_bytes()).decode()
    trace = [{"id": "1", "role": "user", "text": args.brief[:2400]}]
    if args.note:
        trace.append({"id": "2", "role": "assistant", "text": args.note[:2400]})
    body = {
        "brief": args.brief,
        "trace": trace,
        "trace_complete": args.final,
        "html": html[:8000],
        "screenshot_base64": shot,
        "ref": args.page.name,
    }
    request = urllib.request.Request(
        os.environ.get("STASH_URL", "http://127.0.0.1:3495").rstrip("/") + "/api/v1/taste/predict",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"Grader error {exc.code}: {exc.read().decode()[:500]}")

    verdict = "APPROVED" if result.get("approved") else "NOT APPROVED YET"
    print(f"{verdict} — score {round(result['score'] * 100)}/100")
    print(result.get("summary", ""))
    for i, fix in enumerate(result.get("fixes") or [], 1):
        print(f"{i}. {fix['issue']}\n   -> {fix['fix']}")
    for keep in result.get("keep") or []:
        print(f"keep: {keep}")


if __name__ == "__main__":
    main()
