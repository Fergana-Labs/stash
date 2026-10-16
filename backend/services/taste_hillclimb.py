"""Hill-climb a website against the user's taste grader, side by side with no grader.

Two agents get the same brief. Each writes a self-contained HTML page, which is
rendered with JavaScript and network disabled. The "grader" agent then receives
the grader's verbal feedback and revises until the grader approves or the round
budget runs out. The "alone" agent receives only a generic request to improve,
for as many rounds as the graded agent used. Both are scored by the same grader
so the difference is visible; only the graded agent sees the feedback.

Progress is written to a JSON file after every round so the UI can poll it.
"""

import asyncio
import hashlib
import json
import re
import shutil
from pathlib import Path

from ..config import settings
from . import taste_demo

MAX_ROUNDS = 5
ARMS = ("grader", "alone")

GENERATOR = """You are a coding agent building a web page for a user. Write one complete, \
self-contained HTML document: inline CSS only, no JavaScript, no external fonts, images or \
links. It is viewed at 1440x960. Use plausible, specific content. Return only the HTML, \
starting with <!doctype html> and ending with </html>."""

ALONE_FEEDBACK = "Review your page and make it look better. Return the full revised HTML."


def _feedback(result: dict) -> str:
    lines = [
        f"I checked the page with the user's design grader. Score {round(result['score'] * 100)}/100, "
        f"not approved yet. {result['summary']}",
        "Fix these, most important first:",
        *(f"- {f['issue']} -> {f['fix']}" for f in result["fixes"]),
    ]
    if result.get("keep"):
        lines += ["Keep:", *(f"- {k}" for k in result["keep"])]
    lines.append("Return the full revised HTML.")
    return "\n".join(lines)


async def _generate(messages: list[dict]) -> str:
    from anthropic import AsyncAnthropic

    from scripts.website_taste.runtime import html_only

    reply = await AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY).messages.create(
        model=settings.ANTHROPIC_FAST_MODEL,
        max_tokens=12000,
        system=GENERATOR,
        messages=messages,
    )
    text = "".join(c.text for c in reply.content if c.type == "text")
    return html_only(text)


def _render(html: str, directory: Path) -> Path:
    from scripts.website_taste.runtime import render

    digest = hashlib.sha256(html.encode()).hexdigest()
    source = directory / f"{digest}.html"
    source.write_text(html)
    out = directory / f"{digest}.render.png"
    render(source, out)
    return out


class Run:
    def __init__(self, state_file: Path, runtime: Path, brief: str):
        self.state_file, self.runtime = state_file, runtime
        self.state = {
            "brief": brief,
            "status": "running",
            "threshold": taste_demo.APPROVE,
            "arms": {arm: {"status": "running", "rounds": []} for arm in ARMS},
        }
        self.save()

    def save(self):
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.replace(self.state_file)

    async def arm(self, name: str, model: dict, references, finished: asyncio.Event, rounds_used):
        arm = self.state["arms"][name]
        messages = [{"role": "user", "content": self.state["brief"]}]
        try:
            for n in range(1, MAX_ROUNDS + 1):
                if name == "alone" and finished.is_set() and n > rounds_used[0]:
                    break
                arm["working"] = "Writing the page" if n == 1 else "Revising"
                self.save()
                html = await _generate(messages)
                arm["working"] = "Checking with the grader"
                self.save()
                png = await asyncio.to_thread(_render, html, self.runtime)
                item = {
                    "brief": self.state["brief"],
                    "trace": [{"role": "user", "text": self.state["brief"]}],
                    "trace_complete": False,
                }
                result = await taste_demo.judge(model, item, png, references)
                sha = hashlib.sha256(png.read_bytes()).hexdigest()
                shutil.copyfile(png, self.runtime / f"{sha}.png")
                arm["rounds"].append({"round": n, "screenshot_sha256": sha, **result})
                self.save()
                messages.append({"role": "assistant", "content": html})
                if name == "grader":
                    rounds_used[0] = n
                    if result["approved"]:
                        break
                    messages.append({"role": "user", "content": _feedback(result)})
                else:
                    messages.append({"role": "user", "content": ALONE_FEEDBACK})
            arm["status"] = "done"
        except Exception as exc:  # noqa: BLE001 -- shown in the UI; the other arm continues
            arm["status"] = "failed"
            arm["error"] = re.sub(r"sk-[A-Za-z0-9_-]+", "[key]", str(exc))[:300]
        finally:
            arm.pop("working", None)
            if name == "grader":
                finished.set()
            self.save()


async def run(state_file: Path, runtime: Path, brief: str, model: dict, references) -> dict:
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    job = Run(state_file, runtime, brief)
    finished, rounds_used = asyncio.Event(), [MAX_ROUNDS]
    await asyncio.gather(
        *(job.arm(name, model, references, finished, rounds_used) for name in ARMS)
    )
    job.state["status"] = (
        "done" if any(a["status"] == "done" for a in job.state["arms"].values()) else "failed"
    )
    job.save()
    return {
        name: {
            "rounds": len(a["rounds"]),
            "final": a["rounds"][-1]["score"] if a["rounds"] else None,
        }
        for name, a in job.state["arms"].items()
    }
