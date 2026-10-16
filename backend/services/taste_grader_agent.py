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
        "zoom in before reporting it. Any claim about sizes, widths, proportions or alignment "
        "must be checked with measure or inspect_region first; never report one by eye. Grade only what the task says the agent built; if the task "
        "names a shared app shell (sidebar, top bar), ignore it entirely: don't score it or ask to "
        "change it. Before each tool call, write one short line saying what you are checking. "
        "Use a handful of tools, then call verdict.",
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

HISTORY = """Your previous checks of this page, oldest first. Grade the page fresh against \
all their preferences first; use this history only afterwards, to check earlier issues. \
Treat it as claims to re-check, not facts: earlier checks can be wrong. Verify each earlier issue against the page \
as it is now; drop any you cannot confirm with a look, zoom or measurement, and say so. What \
you see now always wins over history. Don't flag something you told them to keep unless it \
got worse. Raise a new issue only if it matters as much as the earlier ones. If the agent \
fixed what you asked and nothing major remains, the score should go up.
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
        "description": "Screenshot one region of the window at 2x resolution. x, y, width and height are CSS pixels in the window as it appears at scroll_y (the main content's scroll position; omit to keep the current one). Use the scroll position of the look where you saw the region.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer", "minimum": 20},
                "height": {"type": "integer", "minimum": 20},
                "scroll_y": {"type": "integer", "minimum": 0},
            },
            "required": ["x", "y", "width", "height"],
        },
    },
    {
        "name": "inspect_region",
        "description": "List the visible elements inside a window region (same coordinates as zoom), with their boxes in CSS pixels, background color, border, corner radius and any text. Use it to measure non-text things like bar widths, dot sizes and gaps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "scroll_y": {"type": "integer", "minimum": 0},
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
                            "breaks_direct_rule": {
                                "type": "boolean",
                                "description": "True if this breaks a preference marked [they said this directly]. Check those rules by measuring.",
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
  if (panels[0]) { panels[0].scrollTop = y; return Math.round(panels[0].scrollTop); }
  window.scrollTo(0, y);
  return Math.round(window.scrollY);
}"""

CURRENT_SCROLL = """() => {
  const panels = [...document.querySelectorAll("*")].filter((el) => {
    const s = getComputedStyle(el);
    return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 4;
  });
  panels.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight);
  return Math.round(panels[0] ? panels[0].scrollTop : window.scrollY);
}"""

INSPECT = r"""([x, y, w, h]) => {
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || r.right < x || r.left > x + w || r.bottom < y || r.top > y + h) continue;
    if (r.width > w * 1.5 && r.height > h * 1.5) continue; // containers bigger than the region
    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "none") continue;
    // Concatenate text pieces as the browser does: React splits "v{n}" into "v" and "3".
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").replace(/\s+/g, " ").trim();
    const painted = s.backgroundColor !== "rgba(0, 0, 0, 0)" || s.borderTopWidth !== "0px" || el.tagName === "svg" || el.tagName === "IMG";
    if (!own && !painted) continue;
    out.push({ tag: el.tagName.toLowerCase(), left: Math.round(r.left), top: Math.round(r.top),
      width: Math.round(r.width * 10) / 10, height: Math.round(r.height * 10) / 10,
      background: painted ? s.backgroundColor : undefined, text: own.slice(0, 40) || undefined,
      radius: s.borderRadius !== "0px" ? s.borderRadius : undefined,
      border: s.borderTopWidth !== "0px" ? s.borderTopWidth : undefined });
    if (out.length >= 80) break;
  }
  return out;
}"""

MEASURE = r"""(texts) => {
  const ctx = document.createElement("canvas").getContext("2d");
  return texts.map((needle) => {
    const all = [...document.querySelectorAll("body *")].filter((el) => {
      if (!el.textContent || !el.textContent.includes(needle)) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });
    // The innermost elements that contain the text.
    const hits = all.filter((el) => ![...el.children].some((c) => all.includes(c))).slice(0, 3);
    return { text: needle, matches: hits.map((el) => {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      // Baseline from the glyphs themselves: the text's line box top plus the font's ascent.
      // Works inside flex and grid layouts, where an inline probe would not sit on the baseline.
      let baseline = null;
      const node = [...el.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
      if (node) {
        const range = document.createRange();
        range.selectNodeContents(node);
        const box = range.getClientRects()[0];
        ctx.font = s.font;
        const m = ctx.measureText(node.textContent.trim());
        if (box) baseline = Math.round((box.top + m.fontBoundingBoxAscent) * 10) / 10;
      }
      return { tag: el.tagName.toLowerCase(), left: Math.round(r.left), top: Math.round(r.top),
        width: Math.round(r.width), height: Math.round(r.height), baseline,
        font_size: s.fontSize, line_height: s.lineHeight, font_weight: s.fontWeight };
    }) };
  });
}"""


def _half(png: bytes) -> bytes:
    """A 2x screenshot scaled to CSS-pixel size, for full-window looks."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(png)) as image:
        small = image.resize((image.width // 2, image.height // 2), Image.LANCZOS)
        buf = io.BytesIO()
        small.save(buf, format="PNG")
    return buf.getvalue()


def _image(png: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(png).decode(),
        },
    }


def fingerprint(model: dict) -> str:
    """Identifies everything that shapes a verdict: rules, instructions, tools, model and
    approval bar. History is only shared between checks with the same fingerprint, so an
    improved grader never inherits verdicts made by an older one."""
    import hashlib

    basis = {
        "rules": model["preferences"],
        "system": SYSTEM,
        "history": HISTORY,
        "tools": TOOLS,
        "model": settings.ANTHROPIC_MODEL,
        "approve": taste_demo.approve_threshold(),
    }
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:16]


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


def grade(
    model: dict, item: dict, url: str, shot_path: Path, refs=(), previous=(), trace_dir=None
) -> dict:
    """Run the grader agent on a live page. Saves its first full look to shot_path.

    With trace_dir, every image the grader sees, every measurement and its notes are
    saved there (trace.json plus numbered PNGs) for inspection."""
    from anthropic import Anthropic
    from playwright.sync_api import sync_playwright

    from scripts.website_taste.autolabel import pixels

    _check_url(url)
    rules = "\n".join(
        f"- {'AVOID' if p['kind'] == 'avoid' else 'PREFER'}: {p['rule']}"
        + (
            " [they said this directly; breaking it blocks approval]"
            if p.get("source") == "feedback"
            else ""
        )
        for p in model["preferences"]
    )

    steps = "\n".join(f"[{s['role']}] {s['text'][:600]}" for s in item["trace"][-12:])
    parsed = urlparse(url)
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            # Rendered at 2x: full-window looks are scaled down, zooms crop real 2x pixels.
            page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
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
            first = _half(page.screenshot(type="png", animations="disabled"))
            shot_path.write_bytes(first)
            trace: list[dict] = []

            def keep_image(png: bytes, label: str) -> str:
                if trace_dir is None:
                    return ""
                name = f"{len(list(trace_dir.glob('*.png'))) + 1:02d}-{label}.png"
                (trace_dir / name).write_bytes(png)
                return name

            def save_trace(extra=None):
                if trace_dir is not None:
                    (trace_dir / "trace.json").write_text(
                        json.dumps({"url": url, "steps": trace, **(extra or {})}, indent=2)
                    )

            if trace_dir is not None:
                trace_dir.mkdir(parents=True, exist_ok=True)
                trace.append({"event": "first screen", "image": keep_image(first, "first-screen")})
                if previous:
                    trace.append({"event": "history given", "text": _history(list(previous))})

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
                    tool_choice={"type": "tool", "name": "verdict"} if forced else {"type": "auto"},
                    messages=messages,
                )
                messages.append({"role": "assistant", "content": reply.content})
                for block in reply.content:
                    if block.type == "text" and block.text.strip():
                        trace.append({"event": "note", "text": block.text.strip()})
                if not any(b.type == "tool_use" for b in reply.content):
                    messages.append({"role": "user", "content": "Use a tool, or call verdict."})
                    continue
                results = []
                for use in (b for b in reply.content if b.type == "tool_use"):
                    args = use.input
                    if use.name == "verdict":
                        verdict = {
                            **_verdict(args, ignore_shell="shared shell" in item["brief"]),
                            "inspected": inspected,
                            "grader": fingerprint(model),
                        }
                        trace.append({"event": "verdict", "raw": args})
                        save_trace({"verdict": verdict})
                        return verdict
                    inspected.append(_describe(use.name, args))
                    trace.append({"event": "tool", "name": use.name, "args": args})
                    try:
                        if use.name == "look":
                            if args.get("width"):
                                page.set_viewport_size({"width": args["width"], "height": 800})
                            scroll = page.evaluate(SCROLL, args.get("scroll_y", 0))
                            page.wait_for_timeout(300)
                            png = _half(page.screenshot(type="png", animations="disabled"))
                            out = [
                                {
                                    "type": "text",
                                    "text": f"Window {page.viewport_size['width']}px wide, scrolled to {scroll}px.",
                                },
                                _image(png),
                            ]
                            trace[-1]["image"] = keep_image(png, "look")
                        elif use.name in ("zoom", "inspect_region"):
                            if "scroll_y" in args:
                                page.evaluate(SCROLL, args["scroll_y"])
                                page.wait_for_timeout(300)
                            scroll = page.evaluate(CURRENT_SCROLL)
                            box = [args["x"], args["y"], args["width"], args["height"]]
                            if use.name == "zoom":
                                clip = dict(zip(("x", "y", "width", "height"), box))
                                png = page.screenshot(type="png", clip=clip)
                                out = [
                                    {
                                        "type": "text",
                                        "text": f"Region at scroll position {scroll}px, 2x:",
                                    },
                                    _image(png),
                                ]
                                trace[-1]["image"] = keep_image(png, "zoom")
                            else:
                                found = page.evaluate(INSPECT, box)
                                out = json.dumps({"scroll_position": scroll, "elements": found})
                                trace[-1]["result"] = found
                        else:
                            out = json.dumps(page.evaluate(MEASURE, args["texts"]))
                            trace[-1]["result"] = json.loads(out)
                    except Exception as exc:  # noqa: BLE001 -- the grader sees the error and moves on
                        out = f"Error: {str(exc)[:300]}"
                        trace[-1]["error"] = out
                    results.append({"type": "tool_result", "tool_use_id": use.id, "content": out})
                messages.append({"role": "user", "content": results})
        finally:
            browser.close()
    raise ValueError("The grader did not reach a verdict.")


def _describe(name: str, args: dict) -> str:
    if name == "look":
        where = f" scrolled to {args['scroll_y']}px" if args.get("scroll_y") else ""
        width = f"{args['width']}px wide" if args.get("width") else "the window"
        return f"looked at {width}{where}"
    if name in ("zoom", "inspect_region"):
        where = f" scrolled to {args['scroll_y']}px" if "scroll_y" in args else ""
        verb = "zoomed into" if name == "zoom" else "inspected"
        return f"{verb} {args['width']}x{args['height']} at ({args['x']}, {args['y']}){where}"
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
    # Major execution flaws and anything breaking a rule the user stated directly
    # are dealbreakers: they can never be approved.
    flawed = any(
        (f.get("kind") == "execution" and f.get("major")) or f.get("breaks_direct_rule")
        for f in fixes
    )
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
                "major": bool(
                    (f.get("kind") == "execution" and f.get("major")) or f.get("breaks_direct_rule")
                ),
            }
            # Execution fixes first: they are what blocks approval.
            for f in sorted(
                args["fixes"], key=lambda f: not (f.get("kind") == "execution" and f.get("major"))
            )[:5]
        ],
        "keep": [str(k)[:200] for k in args.get("keep", [])[:3]],
        "note": "Graded by your taste grader, which inspected the live page.",
    }
