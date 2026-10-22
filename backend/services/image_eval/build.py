"""Build a taste classifier in one step: style brief, imitations, training.

Trained only on liked images versus unrelated disliked ones, a classifier learns
"this person's taste versus generic", and every reasonable imitation scores near
1, so an agent optimizing against it gets no signal. The build closes that gap
without asking the owner to label anything:

1. Style brief: Claude studies the liked examples (whole and as full-resolution
   close-ups) against the disliked ones and writes down what defines the style,
   plus subjects typical of it. Comments on every later score start from it.
2. Imitations: for each subject Claude draws one imitation as plain SVG, using the
   brief and a few liked examples. The server rasterizes it with resvg (no scripts,
   no network, no external files) and adds it as a disliked example with source
   'imitation'.
3. Training on liked versus disliked-plus-imitations, so the score reads as "how
   indistinguishable from the liked examples".

Runs as a Celery task on the reward queue; progress is stored in
image_evals.build for the page to poll.
"""

import asyncio
import json
import logging
import random
import re
from pathlib import Path
from uuid import UUID

import numpy as np

from ...database import get_pool
from .. import llm
from . import critic, embedder, service

logger = logging.getLogger(__name__)
IMITATIONS = 12
REFS_PER_IMITATION = 4
CONCURRENCY = 4
SIDE = 1024
FONT = Path(__file__).parent / "fonts" / "GochiHand-Regular.ttf"
BRIEF_REFS = 8
BRIEF_CLOSEUPS = 4
BRIEF_CONTRAST = 4

BRIEF_SYSTEM = """You study one person's taste from images they like and images they don't. \
Write the style brief a skilled illustrator or designer would need to make new work this \
person would mistake for one of their liked examples. Be concrete and visual: line work \
(weight, wobble, tapering, how texture like hair or fur is built), color and fills, how \
characters and faces are drawn, lettering and the voice of any text, composition and empty \
space, and what separates the liked images from the disliked ones. Use the close-ups for \
mark-making detail. No generic words like "clean" or "modern" without saying what they look \
like here.

Return only JSON: {"brief": str (markdown bullets, under 350 words), "subjects": [str] \
(%d short, varied subjects typical of the liked examples, each one line)}"""

IMITATE_SYSTEM = """You are an illustrator imitating a style as closely as you can. Draw \
the given subject in the style of the reference images, following the style brief. Output \
ONE self-contained SVG, viewBox 0 0 1024 1024, with a background rect. Use only SVG shapes, \
paths and text: no <image>, <script>, <foreignObject>, external references or CSS imports. \
For hand lettering use font-family "Gochi Hand". Imitate the mark-making, not just the \
layout: build texture from many small strokes where the references do. Never add a \
signature, handle or watermark.

Reply with the SVG only, in a single ```svg block."""


async def _set(classifier_id: UUID, **build) -> None:
    await get_pool().execute(
        "UPDATE image_evals SET build = coalesce(build, '{}'::jsonb) || $2::jsonb, updated_at=now() WHERE id=$1",
        classifier_id,
        build,
    )


async def _ask(system: str, content: list, max_tokens: int) -> str:
    async with llm._get_client().messages.stream(
        model=critic.model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        reply = await stream.get_final_message()
    return "".join(b.text for b in reply.content if b.type == "text")


async def write_brief(classifier_id: UUID, liked: list[bytes], disliked: list[bytes]) -> dict:
    rng = random.Random(str(classifier_id))
    refs = rng.sample(liked, min(BRIEF_REFS, len(liked)))
    contrast = rng.sample(disliked, min(BRIEF_CONTRAST, len(disliked)))
    content: list = [
        {"type": "text", "text": "Images they like:"},
        *[critic.jpeg(b, 768) for b in refs],
    ]
    content += [{"type": "text", "text": "Full-resolution close-ups of liked images:"}]
    content += [critic.jpeg(b, 768, crop=True) for b in refs[:BRIEF_CLOSEUPS]]
    if contrast:
        content += [
            {"type": "text", "text": "Images they don't like:"},
            *[critic.jpeg(b, 512) for b in contrast],
        ]
    content.append({"type": "text", "text": "Write the style brief and subjects now."})
    text = await _ask(BRIEF_SYSTEM % IMITATIONS, content, 6000)
    match = re.search(r"\{.*\}", text, re.S)
    parsed = json.loads(match.group(0)) if match else {}
    subjects = [str(s)[:200] for s in parsed.get("subjects", []) if str(s).strip()][:IMITATIONS]
    if not parsed.get("brief") or not subjects:
        raise ValueError("Could not write a style brief from these examples")
    return {"brief": str(parsed["brief"])[:6000], "subjects": subjects}


def sanitize_svg(svg: str) -> str:
    """Drop anything that could load or run something; resvg then only draws shapes and text."""
    for tag in ("script", "foreignObject", "image"):
        svg = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}\s*>", "", svg, flags=re.S | re.I)
        svg = re.sub(rf"</?{tag}\b[^>]*>", "", svg, flags=re.I)
    # Internal references (href="#id", used by <use>) stay; anything pointing elsewhere goes.
    svg = re.sub(r"\s(xlink:)?href\s*=\s*(\"[^\"#][^\"]*\"|'[^'#][^']*')", "", svg, flags=re.I)
    svg = re.sub(r"@import[^;]*;|url\(\s*['\"]?(?!#)[^)]*\)", "none", svg, flags=re.I)
    return svg


def rasterize(svg: str) -> bytes:
    import resvg_py

    return bytes(
        resvg_py.svg_to_bytes(
            svg_string=sanitize_svg(svg),
            width=SIDE,
            height=SIDE,
            background="white",
            font_files=[str(FONT)],
            skip_system_fonts=False,
            cursive_family="Gochi Hand",
        )
    )


async def imitate(brief: str, subject: str, refs: list[bytes]) -> bytes | None:
    content: list = [
        {"type": "text", "text": "Reference images:"},
        *[critic.jpeg(b, 768) for b in refs],
    ]
    content.append({"type": "text", "text": f"Style brief:\n{brief}\n\nSubject to draw: {subject}"})
    text = ""
    for attempt in range(2):
        try:
            text = await _ask(IMITATE_SYSTEM, content, 16000)
            break
        except Exception:  # a timeout or API error costs one imitation, not the build
            logger.warning("Imitation request failed (attempt %d)", attempt + 1, exc_info=True)
    match = re.search(r"```svg\s*(.*?)```", text, re.S) or re.search(
        r"(<svg\b.*</svg>)", text, re.S
    )
    if not match:
        return None
    try:
        png = await asyncio.to_thread(rasterize, match.group(1))
    except Exception:  # an unrenderable SVG is one lost imitation, not a failed build
        logger.warning("Imitation SVG failed to render", exc_info=True)
        return None
    return None if await asyncio.to_thread(_blank, png) else png


def _blank(png: bytes) -> bool:
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(png)) as im:
        return float(np.asarray(im.convert("L")).std()) < 2.0


async def run(classifier_id: UUID) -> None:
    row = await get_pool().fetchrow(
        "SELECT owner_user_id FROM image_evals WHERE id=$1", classifier_id
    )
    owner = row["owner_user_id"]
    rows = await get_pool().fetch(
        "SELECT label,image_key FROM image_eval_examples WHERE classifier_id=$1 AND source<>'imitation'",
        classifier_id,
    )
    liked = [await service._read(r["image_key"]) for r in rows if r["label"] == "liked"]
    disliked = [await service._read(r["image_key"]) for r in rows if r["label"] == "disliked"]
    if len(liked) < service.heads.MIN_PER_CLASS:
        raise ValueError(f"Need at least {service.heads.MIN_PER_CLASS} liked examples")

    await _set(classifier_id, stage="brief", done=0, total=IMITATIONS)
    # Uploads are stored unembedded; embed them while Claude studies the style.
    written, _ = await asyncio.gather(
        write_brief(classifier_id, liked, disliked), service.embed_pending(classifier_id)
    )
    await get_pool().execute(
        "UPDATE image_evals SET style_brief=$2 WHERE id=$1", classifier_id, written["brief"]
    )

    await _set(classifier_id, stage="imitations")
    await get_pool().execute(
        "DELETE FROM image_eval_examples WHERE classifier_id=$1 AND source='imitation'", classifier_id
    )
    gate = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def one(i: int, subject: str):
        nonlocal done
        refs = random.Random(f"{classifier_id}-{i}").sample(
            liked, min(REFS_PER_IMITATION, len(liked))
        )
        async with gate:
            png = await imitate(written["brief"], subject, refs)
        done += 1
        await _set(classifier_id, done=done)
        return subject, png

    made = [
        (s, p)
        for s, p in await asyncio.gather(*(one(i, s) for i, s in enumerate(written["subjects"])))
        if p
    ]
    if made:
        vectors = await embedder.embed([p for _, p in made])
        for (subject, png), vector in zip(made, vectors, strict=True):
            key = await service._store(owner, png, "image/png")
            await get_pool().execute(
                """INSERT INTO image_eval_examples (classifier_id,label,source,filename,note,image_key,content_type,embedding)
                VALUES ($1,'disliked','imitation',$2,'',$3,'image/png',$4)""",
                classifier_id,
                subject[:300],
                key,
                vector,
            )

    await _set(classifier_id, stage="training", imitations=len(made))
    await service.train(owner, classifier_id)
    await _set(classifier_id, stage="done", error=None)
