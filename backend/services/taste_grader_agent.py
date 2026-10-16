"""An agent grader that inspects a live page itself (demo mode only).

Instead of judging one screenshot, Claude gets a browser on the page under review:
it can look at any window width and scroll position, zoom into a region at Retina
resolution, and measure elements' boxes, font sizes and baselines. It finishes by
calling `verdict` with the same fields as the screenshot grader.

Only local app URLs (127.0.0.1 / localhost) are opened, and only in demo mode: the
server fetching user-supplied URLs is not safe to enable in production.
"""

import base64
import json
from pathlib import Path
from urllib.parse import quote, urlparse

from ..config import settings
from . import taste_demo

MAX_STEPS = 10
LOCAL_HOSTS = ("127.0.0.1", "localhost")

SYSTEM = (
    taste_demo.JUDGE_SYSTEM.replace(
        "You see the task, what the agent has done so far, and a screenshot of the current work.",
        "You see the task and what the agent has done so far, and you have a browser open on the "
        "page. Inspect it the way they would: look at the full first screen, scroll to see the "
        "rest, zoom in on summary rows, toolbars, chart labels and table headers to check "
        "alignment, wrapping and clipping, and measure items that should share a baseline. Judge "
        "at 1280px wide; that is the window they use. Check execution as carefully as style. "
        "Only report what you actually saw in a look or zoom, or measured: if you are not sure, "
        "zoom in before reporting it. Grade only what the task says the agent built; if the task "
        "names a shared app shell (sidebar, top bar), ignore it entirely: don't score it or ask to "
        "change it. Use a handful of tools, then call verdict.",
    )
    .replace(
        "Return only JSON:",
        "Finish by calling the verdict tool with:",
    )
    .replace(
        "Visible execution flaws block approval: while any remain, score below 70 even if the "
        "style is right.",
        "Mark an execution flaw major only if a person would notice it at a normal glance: text "
        "clipped or overlapping, a row, toolbar or header that wraps onto a second line at 1280px, "
        "or items meant to line up that are off by 3px or more. Everything else is minor. Major "
        "execution flaws block approval; minor ones only cost points.",
    )
)

HISTORY = """Your previous checks of this page, oldest first. Be consistent with them: \
look at whether each earlier fix was made and say so; don't flag something you told them to \
keep unless it got worse; don't repeat a fix that was done. Raise a new issue only if it \
matters as much as the earlier ones. If the agent fixed what you asked and nothing major \
remains, the score should go up.
{checks}"""

TOOLS = [
    {
        "name": "look",
        "description": "Screenshot the visible window. Optionally resize the window, or scroll the main content (in CSS pixels from the top) first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "width": {"type": "integer", "minimum": 360, "maximum": 1920},
                "scroll_y": {"type": "integer", "minimum": 0},
            },
        },
    },
    {
        "name": "zoom",
        "description": "Screenshot one region of the current window at 2x resolution. Coordinates are CSS pixels in the window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer", "minimum": 20},
                "height": {"type": "integer", "minimum": 20},
            },
            "required": ["x", "y", "width", "height"],
        },
    },
    {
        "name": "measure",
        "description": "Find visible elements containing each text and report their boxes, font size, line height and text baseline, in CSS pixels. Use to confirm whether items line up.",
        "input_schema": {
            "type": "object",
            "properties": {"texts": {"type": "array", "items": {"type": "string"}, "maxItems": 12}},
            "required": ["texts"],
        },
    },
    {
        "name": "verdict",
        "description": "Your final grade.",
        "input_schema": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "summary": {"type": "string"},
                "fixes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "issue": {"type": "string"},
                            "fix": {"type": "string"},
                            "kind": {
                                "type": "string",
                                "enum": ["execution", "style"],
                                "description": "execution: misalignment, awkward wrapping, clipping, overlap, inconsistent spacing. style: everything else.",
                            },
                            "major": {
                                "type": "boolean",
                                "description": "Execution flaws only: true if a person would notice it at a normal glance (see the rules).",
                            },
                        },
                        "required": ["issue", "fix", "kind"],
                    },
                },
                "keep": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["score", "summary", "fixes"],
        },
    },
]

# Apps often scroll an inner panel rather than the window: scroll the largest
# scrollable element (or the window when nothing else scrolls).
SCROLL = """(y) => {
  const panels = [...document.querySelectorAll("*")].filter((el) => {
    const s = getComputedStyle(el);
    return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 4;
  });
  panels.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight);
  if (panels[0]) panels[0].scrollTop = y; else window.scrollTo(0, y);
}"""

MEASURE = """(texts) => texts.map((needle) => {
  const all = [...document.querySelectorAll("body *")].filter((el) => {
    if (!el.textContent || !el.textContent.includes(needle)) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
  // The innermost elements that contain the text.
  const hits = all.filter((el) => ![...el.children].some((c) => all.includes(c))).slice(0, 3);
  return { text: needle, matches: hits.map((el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    const probe = document.createElement("span");
    probe.style.cssText = "display:inline-block;width:0;height:0;vertical-align:baseline";
    el.appendChild(probe);
    const baseline = probe.getBoundingClientRect().top;
    probe.remove();
    return { tag: el.tagName.toLowerCase(), left: Math.round(r.left), top: Math.round(r.top),
      width: Math.round(r.width), height: Math.round(r.height), baseline: Math.round(baseline * 10) / 10,
      font_size: s.fontSize, line_height: s.lineHeight, font_weight: s.fontWeight };
  }) };
})"""


def _image(png: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(png).decode(),
        },
    }


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if not taste_demo.enabled() or parsed.scheme != "http" or parsed.hostname not in LOCAL_HOSTS:
        raise ValueError(
            "Only local app pages (http://127.0.0.1/...) can be graded by URL, in demo mode."
        )


def _history(previous: list[dict]) -> str:
    lines = []
    for i, check in enumerate(previous, 1):
        lines.append(f"Check {i}: score {round(check['score'] * 100)}. {check.get('summary', '')}")
        lines += [f"  fix: {f['issue']} -> {f['fix']}" for f in check.get("fixes", [])]
        lines += [f"  keep: {k}" for k in check.get("keep", [])]
    return HISTORY.format(checks="\n".join(lines))


def grade(model: dict, item: dict, url: str, shot_path: Path, refs=(), previous=()) -> dict:
    """Run the grader agent on a live page. Saves its first full look to shot_path."""
    from anthropic import Anthropic
    from playwright.sync_api import sync_playwright

    from scripts.website_taste.autolabel import pixels

    _check_url(url)
    rules = "\n".join(
        f"- {'AVOID' if p['kind'] == 'avoid' else 'PREFER'}: {p['rule']}"
        for p in model["preferences"]
    )
    steps = "\n".join(f"[{s['role']}] {s['text'][:600]}" for s in item["trace"][-12:])
    parsed = urlparse(url)
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
            # The local app signs in through its /local-preview route.
            page.goto(f"http://{parsed.netloc}/local-preview?next={quote(path)}", timeout=60000)
            page.wait_for_url(lambda u: urlparse(u).path != "/local-preview", timeout=60000)
            if urlparse(page.url).path != parsed.path:
                raise ValueError(f"{parsed.path} redirected to {urlparse(page.url).path}.")
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:  # noqa: BLE001 -- polling pages never go idle
                pass
            page.wait_for_timeout(1000)
            first = page.screenshot(type="png", animations="disabled")
            shot_path.write_bytes(first)

            content: list = []
            for label, ref in refs:
                content += [
                    {
                        "type": "text",
                        "text": f"Reference screen they {'liked' if label == 'liked' else 'wanted changed'}:",
                    },
                    pixels(ref),
                ]
            content += [
                {
                    "type": "text",
                    "text": f"Now the work to grade, open in your browser at 1280x800. Task: {item['brief']}"
                    f"\n\nAgent trace so far:\n{steps}\n\n"
                    + (_history(list(previous)) + "\n\n" if previous else "")
                    + "The first screen:",
                },
                _image(first),
            ]
            messages = [{"role": "user", "content": content}]
            inspected: list[str] = []
            for step in range(MAX_STEPS):
                forced = step == MAX_STEPS - 1
                reply = client.messages.create(
                    model=settings.ANTHROPIC_MODEL,
                    max_tokens=2000,
                    system=SYSTEM.format(rules=rules),
                    tools=TOOLS,
                    tool_choice={"type": "tool", "name": "verdict"} if forced else {"type": "any"},
                    messages=messages,
                )
                messages.append({"role": "assistant", "content": reply.content})
                results = []
                for use in (b for b in reply.content if b.type == "tool_use"):
                    args = use.input
                    if use.name == "verdict":
                        return {
                            **_verdict(args, ignore_shell="shared shell" in item["brief"]),
                            "inspected": inspected,
                        }
                    inspected.append(_describe(use.name, args))
                    try:
                        if use.name == "look":
                            if args.get("width"):
                                page.set_viewport_size({"width": args["width"], "height": 800})
                            page.evaluate(SCROLL, args.get("scroll_y", 0))
                            page.wait_for_timeout(300)
                            out = [_image(page.screenshot(type="png", animations="disabled"))]
                        elif use.name == "zoom":
                            # Render the same page at 2x just for this capture.
                            size = page.viewport_size
                            cdp = page.context.new_cdp_session(page)
                            cdp.send(
                                "Emulation.setDeviceMetricsOverride",
                                {**size, "deviceScaleFactor": 2, "mobile": False},
                            )
                            try:
                                clip = {k: args[k] for k in ("x", "y", "width", "height")}
                                out = [_image(page.screenshot(type="png", clip=clip))]
                            finally:
                                cdp.send("Emulation.clearDeviceMetricsOverride")
                                cdp.detach()
                        else:
                            out = json.dumps(page.evaluate(MEASURE, args["texts"]))
                    except Exception as exc:  # noqa: BLE001 -- the grader sees the error and moves on
                        out = f"Error: {str(exc)[:300]}"
                    results.append({"type": "tool_result", "tool_use_id": use.id, "content": out})
                messages.append({"role": "user", "content": results})
        finally:
            browser.close()
    raise ValueError("The grader did not reach a verdict.")


def _describe(name: str, args: dict) -> str:
    if name == "look":
        where = f" scrolled to {args['scroll_y']}px" if args.get("scroll_y") else ""
        return f"looked at {args.get('width', 'the current')}px wide{where}"
    if name == "zoom":
        return f"zoomed into {args['width']}x{args['height']} at ({args['x']}, {args['y']})"
    return "measured " + ", ".join(repr(t) for t in args.get("texts", [])[:4])


# Sloppy execution is a dealbreaker for this person, so it can never be approved.
EXECUTION_CAP = 65


SHELL_WORDS = (
    "sidebar",
    "side bar",
    "top bar",
    "topbar",
    "app shell",
    "navigation rail",
    "page background",
)


def _verdict(args: dict, ignore_shell: bool = False) -> dict:
    raw = max(0, min(100, int(args.get("score", 0))))
    fixes = args.get("fixes", [])
    if ignore_shell:
        # The agent can't change the shared shell; drop requests about it.
        fixes = [
            f
            for f in fixes
            if not any(w in (f.get("issue", "") + f.get("fix", "")).lower() for w in SHELL_WORDS)
        ]
    args = {**args, "fixes": fixes}
    flawed = any(f.get("kind") == "execution" and f.get("major") for f in fixes)
    score = (min(raw, EXECUTION_CAP) if flawed else raw) / 100
    return {
        "label": "liked" if score >= 0.5 else "disliked",
        "score": round(score, 3),
        "approved": score >= taste_demo.approve_threshold(),
        "summary": str(args.get("summary", ""))[:400],
        "fixes": [
            {
                "issue": str(f.get("issue", ""))[:300],
                "fix": str(f.get("fix", ""))[:400],
                "kind": "execution" if f.get("kind") == "execution" else "style",
                "major": bool(f.get("kind") == "execution" and f.get("major")),
            }
            # Execution fixes first: they are what blocks approval.
            for f in sorted(
                args["fixes"], key=lambda f: not (f.get("kind") == "execution" and f.get("major"))
            )[:5]
        ],
        "keep": [str(k)[:200] for k in args.get("keep", [])[:3]],
        "note": "Graded by your taste grader, which inspected the live page.",
    }
