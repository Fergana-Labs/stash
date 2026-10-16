"""Save a web page as a self-contained HTML snapshot for the example-sites upload.

Most app UIs are built by JavaScript, so their saved source is an empty shell.
This loads the page, waits for it to settle, and saves the rendered DOM: scripts
removed, styles kept (CSS-in-JS rules are written out as <style>), and a <base>
plus Chrome's "saved from url" comment so relative assets resolve on upload.

    python -m scripts.website_taste.snapshot_html URL OUT.html [URL OUT.html ...]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SERIALIZE = """() => {
  const doc = document.documentElement.cloneNode(true);
  doc.querySelectorAll("script, noscript, iframe").forEach((n) => n.remove());
  // Rules inserted through the CSSOM (CSS-in-JS) are not in the DOM; write them out.
  const live = [...document.querySelectorAll("style")];
  doc.querySelectorAll("style").forEach((node, i) => {
    try {
      const rules = live[i] && live[i].sheet ? [...live[i].sheet.cssRules].map((r) => r.cssText).join("\\n") : "";
      if (rules.length > node.textContent.length) node.textContent = rules;
    } catch (e) {}
  });
  let head = doc.querySelector("head");
  if (!head) { head = document.createElement("head"); doc.prepend(head); }
  if (!head.querySelector("base")) {
    const base = document.createElement("base");
    base.href = location.href;
    head.prepend(base);
  }
  return "<!DOCTYPE html>\\n" + doc.outerHTML;
}"""


def snapshot(page, url: str) -> str:
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception:  # noqa: BLE001 -- busy pages never go idle; take what loaded
        page.wait_for_timeout(2000)
    html = page.evaluate(SERIALIZE)
    return f"<!-- saved from url=({len(url):04d}){url} -->\n{html}"


def main(args: list[str]) -> None:
    if not args or len(args) % 2:
        raise SystemExit(__doc__)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        for url, out in zip(args[::2], args[1::2]):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(snapshot(page, url))
            print(f"{out}  {Path(out).stat().st_size // 1024} KB")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
