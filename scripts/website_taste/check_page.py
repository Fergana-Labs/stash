"""Check an HTML page against your Stash taste grader, for coding agents.

Renders the page (JavaScript off), sends the screenshot, HTML and brief to the
grader endpoint, and prints the score, whether it is approved, and what to fix.
Each call is saved as an agent check-in on the eval page.

    python -m scripts.website_taste.check_page PAGE.html --brief "What the page is for"
    python -m scripts.website_taste.check_page http://127.0.0.1:3461/some/page --brief "..."

A local URL is opened in the running app, signed in through its /local-preview
route, with JavaScript on. Only localhost addresses are accepted for that mode.

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
from urllib.parse import quote, urlparse

from backend.services.taste import screenshot_page


def screenshot_local_app(url: str, out: Path) -> str:
    """Screenshot a page of the locally running app, signed in. Returns its HTML."""
    from playwright.sync_api import sync_playwright

    parsed = urlparse(url)
    if parsed.hostname not in ("127.0.0.1", "localhost"):
        sys.exit("Only local app URLs (127.0.0.1 or localhost) can be checked this way.")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
            page.goto(f"{origin}/local-preview?next={quote(path)}", timeout=60000)
            page.wait_for_url(lambda u: urlparse(u).path == parsed.path, timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:  # noqa: BLE001 -- polling pages never go idle
                pass
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out), type="png", animations="disabled")
            return page.content()
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("page", help="An HTML file, or a local app URL")
    parser.add_argument("--brief", required=True, help="What the page should be")
    parser.add_argument("--note", default="", help="What you changed since the last check")
    parser.add_argument("--final", action="store_true", help="This is the finished page")
    args = parser.parse_args()

    key = os.environ.get("STASH_API_KEY")
    if not key:
        sys.exit("Set STASH_API_KEY.")
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "page.png"
        if args.page.startswith(("http://", "https://")):
            html = screenshot_local_app(args.page, png)
            ref = urlparse(args.page).path
        else:
            html = Path(args.page).read_text()
            screenshot_page(png, html=html)
            ref = Path(args.page).name
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
        "ref": ref,
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
