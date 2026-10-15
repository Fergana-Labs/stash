"""Build a LOCAL website-design demo with real judge calls and agent revisions.

Remote Claude writes HTML and describes its rendered screenshot; the existing
Jev + small classifier evaluates it. Only a tiny classifier on 16 examples is
fitted locally. No LLM training, local inference model, or GPU job is launched.
All screenshots, provider answers, and candidate revisions are checkpointed.
"""
# ruff: noqa: E402 -- Load the guarded local environment before backend settings.

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/private/tmp/stash-consolidated-local/website-demo")
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)
assert urlsplit(os.environ["DATABASE_URL"]).hostname in ("localhost", "127.0.0.1")
assert urlsplit(os.environ["DATABASE_URL"]).path == "/stash_consolidated_local"
os.environ["EMBEDDING_PROVIDER"] = "none"  # Never load a local embedding model.
os.environ["DB_POOL_MIN"] = "1"
os.environ["DB_POOL_MAX"] = "4"
from backend import database
from backend.config import settings
from backend.services import llm
from backend.services.intuition import builder, curation, fusion, service, wizard
from backend.services.rm import (
    step_labeler,
    step_labeling,
    trace_completion,
    traces,
    workbench,
    workbench_auto,
)
from backend.services.rm.adapters import CanonicalStep, CanonicalTrace

OWNER = UUID(json.loads((OUT.parent / "auth.json").read_text())["id"])
NAME = "[Demo] Website design · Gather"
BRIEF = "Design a polished, distinctive landing page for Gather, a fictional customer-research workspace. People should immediately understand the product and see one clear next action. Prefer an editorial composition, a strong left-aligned headline, disciplined typography, warm neutral colors, purposeful whitespace, restrained corner radii, and a believable product preview. Dislike generic centered gradient heroes, giant pills, competing calls to action, tiny low-contrast text, random decoration, and empty space that pushes the useful content below the fold. No external assets or scripts."
RUBRIC = [
    {
        "id": "hierarchy",
        "type": "noul",
        "prompt": "Does the first screen have a clear visual hierarchy, a specific readable headline, and one dominant next action?",
        "criteria": {
            "true": "The headline, supporting copy, and one main CTA form an obvious reading order.",
            "false": "The headline is vague, visual priorities compete, or several CTAs have equal weight.",
        },
    },
    {
        "id": "craft",
        "type": "noul",
        "prompt": "Are typography, contrast, spacing, alignment, and corner radii disciplined and consistent?",
        "criteria": {
            "true": "Typography is readable, elements align, spacing is purposeful, and corners are restrained.",
            "false": "Low contrast, tiny text, giant pills, arbitrary gaps, or inconsistent treatments dominate.",
        },
    },
    {
        "id": "product",
        "type": "noul",
        "prompt": "Does the first screen show a concrete, believable product preview that explains customer-research work?",
        "criteria": {
            "true": "Specific research projects, customer evidence, or synthesis workflows make the product tangible.",
            "false": "Generic decorative cards, vague claims, or blank space substitute for the product.",
        },
    },
    {
        "id": "distinctive",
        "type": "noul",
        "prompt": "Does the design match the editorial, warm, restrained taste in the reference examples rather than a generic gradient SaaS template?",
        "criteria": {
            "true": "The composition feels deliberately art-directed, with a restrained palette and useful details.",
            "false": "A centered gradient hero, decorative blobs, shiny badges, and generic sales claims dominate.",
        },
    },
]


def reference_html(i: int, liked: bool) -> str:
    palettes = [
        ("#f6f3eb", "#143d31", "#bdcba9"),
        ("#f4f1ea", "#253c51", "#bfcfd8"),
        ("#faf6ed", "#4c382e", "#d7ba9a"),
        ("#f2f2ed", "#2e3a31", "#c2d2b3"),
    ]
    bg, ink, accent = palettes[i % 4]
    brands = [
        "Gather",
        "Commonplace",
        "Fieldnotes",
        "Daybook",
        "Outline",
        "Folio",
        "Tandem",
        "Draft",
    ]
    brand = brands[i % 8]
    headline = [
        "Turn customer conversations into clearer decisions.",
        "Find the signal in every customer conversation.",
        "Your research. One place. A clearer next step.",
        "Keep the whole team close to the customer.",
        "From interviews to insights, without losing the evidence.",
        "Know what your customers are really saying.",
        "A home for the work behind better products.",
        "Make room for a little more understanding.",
    ][i % 8]
    css = f"body{{margin:0;background:{bg};color:{ink};font-family:Arial,sans-serif}}*{{box-sizing:border-box}}a{{color:inherit;text-decoration:none}}nav{{display:flex;align-items:center;justify-content:space-between;padding:30px 6%;border-bottom:1px solid {ink}22}}.brand{{font-size:25px;letter-spacing:-1px;font-weight:700}}.links{{display:flex;gap:30px;font-size:14px}}.button{{display:inline-block;background:{ink};color:{bg};padding:16px 23px;border-radius:4px;font-size:14px}}main{{display:grid;grid-template-columns:1fr 1fr;align-items:center;gap:65px;padding:92px 6% 60px}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:2px;margin-bottom:25px}}h1{{font-family:Georgia,serif;font-weight:400;font-size:{65 + i % 3 * 3}px;line-height:1.05;letter-spacing:-2.8px;margin:0 0 25px}}.intro{{font-size:17px;line-height:1.65;max-width:440px;opacity:.8}}.actions{{display:flex;gap:22px;align-items:center;margin:30px 0 20px;font-size:13px}}.fine{{font-size:11px;opacity:.6}}.product{{background:white;border:1px solid {ink}25;border-radius:6px;box-shadow:0 22px 70px {ink}12;transform:rotate({(i % 3 - 1) * 1.2}deg);overflow:hidden}}.product-head{{display:flex;align-items:center;justify-content:space-between;padding:20px;border-bottom:1px solid #ddd;font-size:13px}}.workspace{{display:grid;grid-template-columns:105px 1fr;min-height:380px}}aside{{background:#f7f8f5;padding:22px 12px;font-size:11px;line-height:2.8;border-right:1px solid #eee}}article{{padding:25px 22px}}h2{{font-size:20px;margin:0 0 9px;letter-spacing:-.6px}}.muted{{font-size:11px;color:#7d847e}}.stats{{display:flex;gap:32px;padding:22px 0}}.stat b{{font-size:25px;display:block}}.stat span{{font-size:10px;opacity:.7}}.quote{{font-family:Georgia,serif;background:{accent}55;padding:20px;font-size:19px;line-height:1.4;border-left:2px solid {ink}}}.row{{padding:15px 0;border-bottom:1px solid #e7e7e0;display:flex;justify-content:space-between;font-size:11px}}.badge{{border:1px solid #cbd5c6;border-radius:3px;padding:3px 6px;font-size:9px}}footer{{padding:30px 6%;display:flex;align-items:center;justify-content:space-between;border-top:1px solid {ink}22;font-size:11px;letter-spacing:1px}}.logos{{display:flex;gap:35px;opacity:.55;font-size:16px;font-weight:bold}}"
    if not liked:
        flaws = [
            "main{display:block;text-align:center;padding:120px 20px}.product{display:none}h1{font:700 95px Arial;letter-spacing:-5px}.button{border-radius:100px;background:#7a30f7}.intro{margin:auto}.actions{justify-content:center}body{background:linear-gradient(130deg,#e6dcff,#d9efff)}",
            "h1{font-size:35px;line-height:1.6}.intro{font-size:11px;color:#bbb}.product{transform:rotate(9deg);border-radius:55px}.button{border-radius:90px}main{gap:150px;padding-top:170px}",
            "main{display:flex;flex-direction:column;text-align:center;padding-top:80px}h1{font:800 80px Arial;color:#a954d8}.intro{max-width:900px}.product{width:220px;height:130px}.actions{justify-content:center;gap:5px}.button{border-radius:40px;background:linear-gradient(45deg,#635bff,#ff61c4);box-shadow:0 15px 30px #8d63ed77}body{background:#faf4ff}",
            "main{padding:40px 2%;gap:15px;grid-template-columns:3fr 1fr}h1{font:900 110px Arial;line-height:.9;letter-spacing:-7px}.intro{font-size:12px;max-width:900px}.product{border-radius:30px;opacity:.45}.actions .button{background:#e92586;border-radius:50px}nav{padding:15px 2%;background:#311958;color:white}",
            "main{grid-template-columns:1fr;padding-top:160px;text-align:center}.product{display:none}.intro{margin:0 auto;color:#b5b5b5}.actions{justify-content:center}.button{border-radius:100px}h1{font:700 84px Arial;color:#45434b}footer{margin-top:150px}",
            "body{background:linear-gradient(60deg,#ffe0ed,#e6d9ff,#dbf3ff)}main{display:block;text-align:center}.product{display:none}h1{font:700 96px Arial}.intro{margin:auto}.button{padding:30px 45px;border-radius:90px;background:#9755ed}.actions{justify-content:center}.fine{color:#c1aecb}",
            "main{grid-template-columns:1fr 1fr;gap:130px;padding-top:150px}h1{font:700 42px Arial;line-height:1.5}.intro{color:#aaa;font-size:12px}.product{box-shadow:15px 20px 0 #a8e3ee;transform:rotate(-8deg);border-radius:65px}.button{border-radius:90px;background:#b7459a}",
            "main{display:block;text-align:center;padding:160px 25%}h1{font:700 45px Arial}.intro{color:#aaa;font-size:13px}.product{display:none}.actions{display:block}.button{margin:12px;border-radius:80px}footer{margin-top:150px}",
        ]
        css += flaws[i % 8]
        headline = [
            "The future of work is here.",
            "Revolutionize everything with AI.",
            "Unlock your unlimited potential.",
            "Your all-in-one solution.",
            "Meet your next superpower.",
            "Everything you need. And more.",
            "A smarter way to do everything.",
            "Transform your workflow today.",
        ][i % 8]
    actions = (
        '<a class="button" href="#">Start your research</a><a href="#">See how it works ↗</a>'
        if liked
        else '<a class="button" href="#">Get started</a><a class="button" href="#">Book a demo</a><a class="button" href="#">Learn more</a>'
    )
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{brand} — customer research</title><style>{css}</style></head><body><nav><div class="brand">{brand}<span style="color:{accent}"> ●</span></div><div class="links"><a href="#">Product</a><a href="#">Resources</a><a href="#">Pricing</a></div><a class="button" href="#">Get started ↗</a></nav><main><section><div class="eyebrow">For teams that listen</div><h1>{headline}</h1><p class="intro">Bring interviews, notes, and customer evidence together. Turn what you learn into decisions your whole team can stand behind.</p><div class="actions">{actions}</div><div class="fine">A calmer research workflow. No credit card required.</div></section><div class="product"><div class="product-head"><b>◉ {brand} workspace</b><span class="badge">Spring research</span></div><div class="workspace"><aside>⌂ Overview<br>▤ Projects<br>◌ Interviews<br>↗ Insights<br>⋯ Settings</aside><article><h2>Understanding our customers</h2><div class="muted">Last updated 2 hours ago · Product team</div><div class="stats"><div class="stat"><b>24</b><span>CONVERSATIONS</span></div><div class="stat"><b>8</b><span>EMERGING THEMES</span></div><div class="stat"><b>3</b><span>DECISIONS READY</span></div></div><div class="quote">“Now we can see the story behind every feature request.”</div><div class="row"><span>Onboarding research</span><span class="badge">Synthesizing</span></div><div class="row"><span>Customer feedback</span><span>12 new notes ↗</span></div></article></div></div></main><footer><span>BUILT FOR TEAMS AT</span><div class="logos"><span>Acorn</span><span>Goodpeople</span><span>Northwind</span><span>Paperplane</span></div><span>More listening. Better decisions.</span></footer></body></html>'


def progress(**data):
    print(json.dumps(data, default=str), flush=True)


async def render(html: str, name: str) -> tuple[Path, str]:
    file = OUT / (name + ".html")
    png = OUT / (name + ".png")
    if file.exists() and file.read_text() != html:
        raise RuntimeError(
            f"Cached source differs for {name}; inspect the saved render before rebuilding"
        )
    file.write_text(html)
    if not png.exists():
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(ROOT / "scripts/render_website_demo.cjs"),
            str(file),
            str(png),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 45)
        if proc.returncode:
            raise RuntimeError(stderr.decode()[:500])
    return png, html


async def image_item(png: Path) -> dict:
    cache = png.with_suffix(".item.json")
    if cache.exists():
        return json.loads(cache.read_text())
    item = await builder.read_input(png.read_bytes(), png.name, "image/png")
    cache.write_text(json.dumps(item))
    progress(phase="image described", file=png.name)
    return item


async def finish_trace(trace_id: UUID):
    """Score explicit fixture labels with native rules and live quality checks."""
    assert settings.TYPESAFE_API_KEY and settings.ANTHROPIC_API_KEY
    pool = database.get_pool()
    trace, steps = await workbench_auto._read_trace(trace_id)
    assert trace["owner_user_id"] == OWNER
    assert trace["metadata"].get("dataset") == "website-design-demo-v1"
    chunks = step_labeler.build_chunks(steps)
    for chunk in chunks:
        step = steps[chunk["idx"]]
        if isinstance((step.get("metadata") or {}).get("label"), dict):
            continue
        label = dict.fromkeys(
            (
                "intent",
                "verdict",
                "verdict_target",
                "sentiment",
                "type",
                "effect",
                "result",
                "is_output",
                "outcome",
                "stance",
                "coverage",
            )
        )
        label.update(
            chunk_id=chunk["chunk_id"],
            actor=chunk["actor"],
            task_id="t1",
            evidence=(chunk.get("result") or chunk.get("text") or "")[:180],
            note="Synthetic demo event annotation. Native rules and live quality checks compute scores.",
        )
        if chunk["actor"] == "user":
            label.update(intent="new_request", verdict="none", sentiment="neutral")
        elif chunk["kind"] == "tool_call":
            label.update(
                type="tool_call",
                is_output=False,
                result="data",
                tool=chunk["tool"],
                effect="read"
                if chunk["tool"] in ("read_file", "browser.screenshot")
                else "side_effect",
                duplicate_of=chunk.get("duplicate_of"),
            )
        elif (step.get("metadata") or {}).get("label_type") == "status_update":
            label.update(type="status_update", is_output=False)
        else:
            label.update(
                type="output", is_output=True, outcome="answer", stance="hedged", coverage="1/1"
            )
        step["metadata"] = {**(step.get("metadata") or {}), "label": label}
        await pool.execute(
            "UPDATE rm_trace_steps SET metadata=$2 WHERE id=$1", step["id"], step["metadata"]
        )
    result = await step_labeling.annotate(trace, steps)
    async with pool.acquire() as conn, conn.transaction():
        for step in steps:
            reward = result["rewards"].get(str(step["idx"]))
            if reward is not None:
                await conn.execute(
                    "UPDATE rm_trace_steps SET metadata=metadata || jsonb_build_object('reward',$2::jsonb) WHERE id=$1",
                    step["id"],
                    reward,
                )
        await conn.execute(
            "UPDATE rm_traces SET metadata=metadata || $2::jsonb WHERE id=$1",
            trace_id,
            {
                "rubric_summary": result["summary"],
                "fixture_annotation_source": "synthetic website-demo-v1",
                "credit_source": "native rules with live Jev quality checks",
            },
        )
        await conn.execute(
            """INSERT INTO rm_step_labels(trace_id,owner_user_id,fingerprint,labels,rewards,summary,chunks,label_model)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(trace_id) DO UPDATE SET
            fingerprint=EXCLUDED.fingerprint,labels=EXCLUDED.labels,rewards=EXCLUDED.rewards,
            summary=EXCLUDED.summary,chunks=EXCLUDED.chunks,label_model=EXCLUDED.label_model,labeled_at=now()""",
            trace_id,
            OWNER,
            step_labeling.fingerprint(steps),
            result["labels"],
            result["rewards"],
            result["summary"],
            {c["chunk_id"]: step_labeling.chunk_hash(c) for c in chunks},
            "synthetic website-demo-v1; live Jev quality checks",
        )
    await workbench.queue_trace(OWNER, trace_id)
    await workbench_auto.process_trace(trace_id)
    evaluation = (await workbench_auto.detail(OWNER, trace_id))["current"]
    if not evaluation or evaluation["status"] != "completed":
        raise RuntimeError("Website trace annotation did not complete; inspect its queue status")
    assert evaluation["credited_actions"] == evaluation["total_actions"]
    completion = await trace_completion.assess(OWNER, trace_id)
    for _ in range(60):
        if completion["tasks"] or not completion["pending"]:
            break
        await asyncio.sleep(3)
        completion = await trace_completion.assess(OWNER, trace_id)
    (OUT / "trace-assessment.json").write_text(
        json.dumps({"evaluation": evaluation, "completion": completion}, default=str, indent=2)
    )
    if not completion["tasks"]:
        raise RuntimeError("Website trace completion estimates are unavailable; inspect assessment")
    progress(
        phase="trace assessed",
        credited=evaluation["credited_actions"],
        actions=evaluation["total_actions"],
        tasks=len(completion["tasks"]),
        checkpoints=sum(len(t["checkpoints"]) for t in completion["tasks"]),
    )


async def main():
    OUT.mkdir(exist_ok=True, parents=True)
    assert settings.ANTHROPIC_API_KEY and settings.TYPESAFE_API_KEY
    await database.init_pool()
    p = database.get_pool()
    try:
        assert await p.fetchval("select current_database()") == "stash_consolidated_local"
        # Cache every provider call; retries resume without repeating completed work.
        gate = asyncio.Semaphore(2)

        async def example(i, liked):
            async with gate:
                name = f"reference-{i + (0 if liked else 8) + 1:02d}"
                png, _ = await render(reference_html(i, liked), name)
                item = await image_item(png)
                return {
                    "item": item,
                    "label": "liked" if liked else "disliked",
                    "split": "eval" if i in (0, 3, 6) else "train",
                    "pinned": i == 1,
                    "note": "Synthetic demo preference. "
                    + (
                        "Clear editorial hierarchy, one main action, readable typography, and a tangible research workspace."
                        if liked
                        else "Generic or vague hero, competing actions, weak contrast, arbitrary spacing, or missing product evidence."
                    ),
                }

        examples = await asyncio.gather(
            *(example(i, liked) for liked in (True, False) for i in range(8))
        )
        mid = await p.fetchval(
            "select id from intuition_models where owner_user_id=$1 and name=$2", OWNER, NAME
        )
        if not mid:
            d = await service.create_model(
                OWNER,
                name=NAME,
                output_type="choice",
                description=BRIEF,
                labels=[
                    {
                        "id": "liked",
                        "description": "I would use this design as a strong reference.",
                    },
                    {
                        "id": "disliked",
                        "description": "I would ask for a redesign before showing this to customers.",
                    },
                ],
                rubric=RUBRIC,
            )
            mid = d["model"]["id"]
            await service.add_examples(OWNER, mid, examples, "generated")
            await curation.save_brief(
                OWNER,
                mid,
                {
                    "decision": "Choose whether a website design matches the founder’s stated visual taste before using it as a customer-facing landing page.",
                    "input": "A screenshot of the first 1440 × 960 pixels of a self-contained HTML website, described by a vision model.",
                    "labels": [
                        {
                            "id": "liked",
                            "means": "Clear, editorial, restrained, and product-specific.",
                            "not": "Merely functional or decorated.",
                        },
                        {
                            "id": "disliked",
                            "means": "Generic, unclear, low-contrast, or visually undisciplined.",
                            "not": "A design that simply uses a different accent color.",
                        },
                    ],
                    "costly_mistake": "Approving a generic or unreadable design is worse than asking for another iteration.",
                    "must_never": [
                        "A centered gradient hero with three equally prominent CTAs is not a liked reference.",
                        "Changing only the accent color should not decide the label.",
                    ],
                    "context": "Synthetic website-design demonstration. Reference labels express a chosen demo preference; no customer data. Judge features come from real screenshot descriptions and real Jev calls.",
                    "success": "Report agreement on held-out designs with the example count. Use the evaluator to compare new candidate designs; it is a small taste classifier, not objective design quality.",
                    "reviewers": ["Demo designer"],
                },
            )
            s = await wizard.create_session(OWNER, mid)
            (OUT / "model.json").write_text(
                json.dumps({"model_id": str(mid), "session_id": s["id"]})
            )
        identity = json.loads((OUT / "model.json").read_text())
        sid = identity["session_id"]
        model = await service._model(OWNER, mid)
        if not model["active_version_id"]:
            report = await fusion.train(
                OWNER,
                mid,
                lambda stage, message, done=0, total=0: progress(
                    phase=stage, message=message, done=done, total=total
                ),
            )
            assert report["gate"]["passed"], report["gate"]
            await service.promote(OWNER, mid)
            (OUT / "training-report.json").write_text(json.dumps(report, default=str, indent=2))
        else:
            report = json.loads((OUT / "training-report.json").read_text())
        progress(
            phase="eval ready",
            held_out=report["holdout"]["n"],
            agreement=report["holdout"]["accuracy"],
        )
        active = (await service.get_detail(OWNER, mid))["active"]
        artifacts = []

        async def score(html, name, iteration):
            png, _ = await render(html, name)
            item = await image_item(png)
            cache = OUT / (name + ".prediction.json")
            if cache.exists():
                prediction = json.loads(cache.read_text())
            else:
                prediction = await service.predict(
                    OWNER,
                    mid,
                    item,
                    caller="website-demo-agent",
                    ref=name,
                    metadata={"synthetic": True, "artifact": name, "iteration": iteration},
                    run="website-design-demo-v1",
                    step=iteration,
                )
                cache.write_text(json.dumps(prediction, default=str))
            result = {
                "iteration": iteration,
                "name": name,
                "html": html,
                "image": item["data_url"],
                "description": item["content"],
                "score": prediction["probabilities"]["liked"],
                "prediction_id": str(prediction["prediction_id"]),
                "rubric": prediction["rubric"],
                "label": prediction["label"],
            }
            progress(
                phase="website scored",
                iteration=iteration,
                score=result["score"],
                label=result["label"],
            )
            artifacts.append(result)
            return result

        baseline = await score(reference_html(0, False), "gather-v0", 0)
        best = baseline
        for iteration in range(1, 4):
            file = OUT / f"gather-v{iteration}.html"
            if file.exists():
                html = file.read_text()
            else:
                feedback = {q["id"]: best["rubric"].get(q["id"]) for q in RUBRIC}
                text = await llm.complete_chat(
                    system="You are a website design agent improving a real HTML file against a personal design evaluator. Return only a complete, self-contained HTML document, with inline CSS and optional inline SVG. No JavaScript, external URLs, fonts, image downloads, or grading claims in the page. Keep the artifact under 22000 characters. Make a substantial, polished visual improvement. Preserve the fictional product Gather and its purpose: a customer-research workspace. The page must fit an effective hero and believable product preview in a 1440x960 viewport.",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": best["image"].split(",", 1)[1],
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": f"DESIGN BRIEF\n{BRIEF}\n\nCURRENT HTML\n{best['html']}\n\nEVALUATOR P(liked)\n{best['score']}\n\nCRITERION FEEDBACK\n{json.dumps(feedback)}\n\nLIKED REFERENCE DESCRIPTION\n{examples[1]['item']['content']}\n\nThis is iteration {iteration}. Improve the weakest aspects; try a materially different composition or more useful product preview rather than superficial decoration. Return HTML only.",
                                },
                            ],
                        }
                    ],
                    tier=llm.ModelTier.QUALITY,
                    max_tokens=8500,
                )
                html = re.sub(r"^```(?:html)?\s*|\s*```$", "", text.strip())
                if "<html" not in html.lower() or len(html) > 60000:
                    raise ValueError("Agent did not return bounded HTML")
                file.write_text(html)
            candidate = await score(html, f"gather-v{iteration}", iteration)
            candidate["accepted"] = candidate["score"] > best["score"]
            if candidate["accepted"]:
                best = candidate
        assert best["iteration"] > 0 and best["score"] > baseline["score"], (
            "No measured improvement; inspect saved candidates"
        )
        # This is a scripted sample conversation about saved, measured artifacts.
        dialogue = [
            (
                "Help me make a website-design eval. I want to show an agent what I like, then have it improve a real HTML page.",
                "Start with the designs you would keep and the ones you would redesign. I will use those judgments to capture your taste, then check it on examples held out from fitting.",
            ),
            (
                "I like a warm, editorial layout, a strong left-aligned headline, clear type, and a real product preview. Avoid giant pills and generic gradient heroes.",
                "That gives us four observable criteria: hierarchy and next action, typography and spacing, product-specific evidence, and the restrained editorial style. I have saved them with the brief.",
            ),
            (
                "Here are eight designs I like and eight I dislike. They are synthetic references for this demo.",
                "The 16 screenshots are saved as editable examples. Their visual descriptions were extracted from the rendered pages, and their labels are the demo preferences you supplied.",
            ),
            (
                "Keep the colors flexible. A website should not fail just because it is blue instead of green.",
                "Agreed. Both labels contain different palettes; the criteria focus on composition, clarity, and execution. I pinned one example of each label and kept six designs held out.",
            ),
            (
                "Create the eval and show the actual check result.",
                f"The fitted evaluator agrees with {round(report['holdout']['accuracy'] * report['holdout']['n'])} of {report['holdout']['n']} held-out labels. This is a small synthetic check, not a guarantee about arbitrary website designs. The version passed its promotion gate and is saved.",
            ),
            (
                "Now use it to improve the Gather landing page. Keep the file and the evaluations so we can see what changed.",
                f"The agent generated three candidate HTML revisions and evaluated each with the saved classifier. It kept a revision only when P(liked) improved. The selected revision is v{best['iteration']}; its actual predictions and source files are attached to the recorded run.",
            ),
        ]
        transcript = []
        messages = []
        for i, (u, a) in enumerate(dialogue):
            transcript.extend(
                [
                    {"role": "user", "kind": "message", "text": u},
                    {"role": "assistant", "parts": [{"type": "text", "text": a}]},
                ]
            )
            messages.extend([{"role": "user", "content": u}, {"role": "assistant", "content": a}])
        await p.execute(
            "update intuition_wizard_sessions set transcript=$2,messages=$3,title=$4 where id=$1",
            UUID(sid),
            transcript,
            messages,
            NAME,
        )
        events = []

        def user(t):
            events.append(CanonicalStep("user", t))

        def say(t):
            events.append(CanonicalStep("assistant", t, metadata={"label_type": "status_update"}))

        def tool(name, args, result):
            cid = f"website-demo-{len(events)}"
            events.extend(
                [
                    CanonicalStep(
                        "assistant", "", tool_name=name, tool_input=args, tool_call_id=cid
                    ),
                    CanonicalStep("tool", result, tool_name=name, tool_call_id=cid),
                ]
            )

        user(
            "Redesign Gather’s landing page to match the liked website examples. Build a personal eval, use it to guide revisions, and keep the initial file and best result for comparison."
        )
        say(
            "I will inspect the initial file, capture a visual baseline, and build the evaluator from the saved reference designs."
        )
        tool("read_file", {"path": "src/index.html"}, baseline["html"])
        tool(
            "browser.screenshot",
            {"file": "src/index.html", "viewport": "1440x960"},
            "Saved gather-v0.png; the actual rendered screenshot is attached to the comparison.",
        )
        tool(
            "create_eval",
            {"name": NAME, "examples": 16, "held_out": 6},
            json.dumps(
                {
                    "model_id": str(mid),
                    "version": active["number"],
                    "held_out_n": report["holdout"]["n"],
                    "agreement": report["holdout"]["accuracy"],
                    "gate_passed": report["gate"]["passed"],
                }
            ),
        )
        for artifact in artifacts:
            if artifact["iteration"]:
                say(
                    f"Iteration {artifact['iteration']}: revise the page using the current evaluator feedback, then render and score the candidate."
                )
                tool(
                    "write_file",
                    {"path": "src/index.html", "revision": artifact["iteration"]},
                    artifact["html"],
                )
                tool(
                    "browser.screenshot",
                    {
                        "file": "src/index.html",
                        "revision": artifact["iteration"],
                        "viewport": "1440x960",
                    },
                    f"Saved {artifact['name']}.png from the candidate HTML.",
                )
            tool(
                "evaluate_website",
                {"model_id": str(mid), "artifact": artifact["name"]},
                json.dumps(
                    {k: artifact[k] for k in ("prediction_id", "score", "label", "rubric")},
                    default=str,
                ),
            )
            if artifact["iteration"]:
                tool(
                    "select_candidate",
                    {"revision": artifact["iteration"]},
                    "Kept as the best so far."
                    if artifact["accepted"]
                    else "Rejected: the incumbent scored higher; retained the previous best.",
                )
        events.append(
            CanonicalStep(
                "assistant",
                f"Selected Gather v{best['iteration']}. P(liked) rose from {baseline['score']:.3f} to {best['score']:.3f} under eval v{active['number']}. The screenshots, HTML, and four prediction records are saved. This is a measured preference-evaluator result on synthetic demo data, not an independent claim of universal design quality.",
            )
        )
        demo = {
            "version": 1,
            "model_id": str(mid),
            "session_id": sid,
            "title": "Gather website redesign",
            "file": "src/index.html",
            "brief": BRIEF,
            "reference_count": 16,
            "held_out_n": report["holdout"]["n"],
            "agreement": report["holdout"]["accuracy"],
            "model_version": active["number"],
            "selected_iteration": best["iteration"],
            "artifacts": artifacts,
            "references": [
                {
                    "image": e["item"]["data_url"],
                    "label": e["label"],
                    "note": e["note"],
                    "split": e["split"],
                }
                for e in examples
            ],
            "criteria": RUBRIC,
            "transcript": transcript,
            "recorded": True,
        }
        old = await p.fetchval(
            "select id from rm_traces where owner_user_id=$1 and external_id='website-design-demo-v1'",
            OWNER,
        )
        if old:
            raise RuntimeError("Demo trace already exists; refusing to replace its steps")
        trace = CanonicalTrace(
            "website-design-demo-v1",
            "[Demo] Website design · eval-guided redesign",
            {
                "agent": "Website design agent",
                "synthetic": True,
                "dataset": "website-design-demo-v1",
                "website_demo": demo,
            },
            events,
        )
        async with p.acquire() as conn, conn.transaction():
            tid = (await traces.store_traces(conn, OWNER, "stash", [trace]))[0]
        (OUT / "manifest.json").write_text(
            json.dumps(
                {
                    "trace_id": str(tid),
                    "model_id": str(mid),
                    "session_id": sid,
                    "selected_iteration": best["iteration"],
                    "before_score": baseline["score"],
                    "after_score": best["score"],
                    "url": f"http://127.0.0.1:3457/reward-models/demos/website/{tid}",
                },
                indent=2,
            )
        )
        progress(
            phase="demo saved",
            trace_id=tid,
            before=baseline["score"],
            after=best["score"],
            steps=len(events),
        )
        await finish_trace(tid)
    finally:
        await database.close_db()


if __name__ == "__main__":
    asyncio.run(main())
