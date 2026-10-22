"""The score and the written feedback for an image, from one Claude call.

Claude sees liked examples (whole and as full-resolution close-ups, so line texture is
visible), the style brief, notes people left when labeling earlier calls, and the image.
It grades the image 1-5 on each trait that defines the style and names the most
important fixes. The score is the mean grade scaled to 0-1.

Why not the embedding classifier: on Henry's judgments (draw-agent-toy/bench) it scored
image-model fakes of the style 0.98-1.00 and ranked his liked drafts below his disliked
ones (AUC 0.19), while these trait grades separated them (AUC 0.95; 0.98 on agent
drafts) and moved about 0.05 when the same image was scored twice.
"""

import base64
import json
import logging
import os
import random
import re
from io import BytesIO
from uuid import UUID

import numpy as np
from PIL import Image

from ...config import settings
from ...database import get_pool
from .. import llm

logger = logging.getLogger(__name__)
REFERENCES = 6
CLOSEUPS = 2
NOTES = 12
ATTEMPTS = 2


class JudgeUnavailable(RuntimeError):
    """The score could not be computed; callers should retry rather than get a made-up number."""


SYSTEM = """You judge how closely an image matches one person's style, as shown by examples they gave. You get their examples, close-ups of them, a description of the style, notes they wrote about earlier images, and the image to judge. Grade the image on each trait of the style from 1 to 5:
5 = indistinguishable from their own examples on this trait
4 = close; a careful eye would spot small differences
3 = recognizably aiming for it, clearly not their hand
2 = only loosely related
1 = absent or contradicted
Judge how it is made, not what it shows. Ignore signatures, handles, watermarks and logos, and never ask for one: copying an artist's signature onto someone else's work is forgery, not style.

%s

Return only JSON: {"traits": [{"trait": str, "score": int, "why": str (under 15 words)}] (6-8 traits that define this style: line work, color and fills, faces and figures, lettering, composition, texture...)%s}"""

FIXES = """Then name the most important differences as fixes someone making it could act on (which element, what is wrong, what the examples do instead). Mention what already matches only if it is worth keeping."""
FIXES_JSON = """, "summary": str (one sentence), "fixes": [{"issue": str, "fix": str}] (1-4, most important first), "keep": [str] (0-2)"""


def jpeg(data: bytes, side: int, crop: bool = False) -> dict:
    with Image.open(BytesIO(data)) as im:
        im = im.convert("RGB")
        if crop:
            im = _closeup(im)
        im.thumbnail((side, side))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.b64encode(buf.getvalue()).decode(),
        },
    }


def _closeup(im: Image.Image, side: int = 640) -> Image.Image:
    """The square crop with the most colored ink: drawn detail rather than typed captions."""
    hsv = np.asarray(im.convert("HSV"), dtype=np.float32)
    mask = (hsv[..., 1] > 50) & (hsv[..., 2] > 60) & (hsv[..., 2] < 245)
    if not mask.any():
        mask = np.asarray(im.convert("L")) < 140
    h, w = mask.shape
    side = min(side, h, w)
    step = max(1, side // 4)
    best, at = -1.0, (0, 0)
    for y in range(0, h - side + 1, step):
        for x in range(0, w - side + 1, step):
            d = mask[y : y + side, x : x + side].mean()
            if d > best:
                best, at = d, (x, y)
    return im.crop((at[0], at[1], at[0] + side, at[1] + side))


def model() -> str:
    """IMAGE_EVAL_MODEL overrides the backend's default model for taste work (briefs, imitations, comments)."""
    return os.environ.get("IMAGE_EVAL_MODEL") or settings.ANTHROPIC_MODEL


async def judge(classifier_id: UUID, name: str, data: bytes, with_fixes: bool = True) -> dict:
    """{"score": 0-1, "traits": [...], "summary", "fixes", "keep"}; raises JudgeUnavailable."""
    from .service import _read

    refs = await get_pool().fetch(
        "SELECT id,image_key FROM image_eval_examples WHERE classifier_id=$1 AND label='liked' AND source='upload' ORDER BY id",
        classifier_id,
    )
    refs = random.Random(str(classifier_id)).sample(list(refs), min(REFERENCES, len(refs)))
    ref_bytes = [await _read(r["image_key"]) for r in refs]
    notes = await get_pool().fetch(
        """SELECT label,note FROM image_eval_examples WHERE classifier_id=$1 AND note<>''
        ORDER BY created_at DESC LIMIT $2""",
        classifier_id,
        NOTES,
    )
    brief = await get_pool().fetchval(
        "SELECT style_brief FROM image_evals WHERE id=$1", classifier_id
    )
    content: list = [{"type": "text", "text": f"Their examples for '{name}':"}]
    content += [jpeg(b, 512) for b in ref_bytes]
    if ref_bytes:
        content.append({"type": "text", "text": "Close-ups of their examples:"})
        content += [jpeg(b, 768, crop=True) for b in ref_bytes[:CLOSEUPS]]
    if brief:
        content.append({"type": "text", "text": f"The style:\n{brief}"})
    if notes:
        content.append(
            {
                "type": "text",
                "text": "Their notes on earlier images:\n"
                + "\n".join(f"- ({n['label']}) {n['note']}" for n in notes),
            }
        )
    content += [{"type": "text", "text": "Image to judge:"}, jpeg(data, 1024)]
    system = SYSTEM % (FIXES if with_fixes else "", FIXES_JSON if with_fixes else "")
    for attempt in range(ATTEMPTS):
        try:
            reply = await llm._get_client().messages.create(
                model=model(),
                max_tokens=3000,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            text = "".join(b.text for b in reply.content if b.type == "text")
            parsed = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            traits = [
                {
                    "trait": str(t["trait"])[:80],
                    "score": int(t["score"]),
                    "why": str(t.get("why", ""))[:200],
                }
                for t in parsed["traits"]
                if isinstance(t, dict) and 1 <= int(t.get("score", 0)) <= 5
            ]
            if not traits:
                raise ValueError("no trait grades")
            return {
                "score": (float(np.mean([t["score"] for t in traits])) - 1) / 4,
                "traits": traits,
                "summary": str(parsed.get("summary", ""))[:600],
                "fixes": [
                    {"issue": str(f.get("issue", ""))[:600], "fix": str(f.get("fix", ""))[:600]}
                    for f in parsed.get("fixes", [])[:4]
                    if isinstance(f, dict)
                ],
                "keep": [str(k)[:300] for k in parsed.get("keep", [])[:2]],
            }
        except Exception:
            logger.warning(
                "Image eval judge failed for %s (attempt %d)",
                classifier_id,
                attempt + 1,
                exc_info=True,
            )
    raise JudgeUnavailable("Couldn't score this image right now; try again")
