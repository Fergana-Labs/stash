"""Written feedback to go with a taste score: what separates this image from the liked examples.

Claude sees a few liked examples (whole and as full-resolution close-ups, so line
texture is visible), the notes people left when labeling earlier calls, the score,
and the image, and names the 1-4 most important differences as concrete fixes.
Comments are best-effort: a failure here never fails the score.
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
REFERENCES = 4
CLOSEUPS = 2
NOTES = 12

SYSTEM = """You review images for how closely they match one person's taste, as shown by \
examples they liked. You get liked examples, full-resolution close-ups of them, a style \
brief, notes the person wrote about earlier images, a score from a classifier trained on their labels (0-1, \
higher = closer to what they like), and the image to review.

Name the most important differences between the image and what they like, as fixes someone \
making it could act on (which element, what is wrong, what the liked examples do instead). \
Mention what already matches only if it is worth keeping. Do not judge the subject matter. \
Ignore signatures, handles, watermarks and logos: never ask for one, since copying an artist's \
signature onto someone else's work is forgery, not style.

Return only JSON: {"summary": str (one sentence), "fixes": [{"issue": str, "fix": str}] \
(1-4, most important first), "keep": [str] (0-2)}"""


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


async def comments(
    classifier_id: UUID, name: str, data: bytes, content_type: str, score: float
) -> dict | None:
    from .service import _read

    try:
        refs = await get_pool().fetch(
            "SELECT id,image_key FROM image_eval_examples WHERE classifier_id=$1 AND label='liked' ORDER BY id",
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
        content: list = [{"type": "text", "text": f"Liked examples for '{name}':"}]
        content += [jpeg(b, 768) for b in ref_bytes]
        if ref_bytes:
            content.append({"type": "text", "text": "Close-ups of liked examples:"})
            content += [jpeg(b, 768, crop=True) for b in ref_bytes[:CLOSEUPS]]
        if brief:
            content.append({"type": "text", "text": f"Style brief for what they like:\n{brief}"})
        if notes:
            content.append(
                {
                    "type": "text",
                    "text": "Their notes on earlier images:\n"
                    + "\n".join(f"- ({n['label']}) {n['note']}" for n in notes),
                }
            )
        content += [
            {"type": "text", "text": f"Classifier score: {score:.2f}. Image to review:"},
            jpeg(data, 1024),
        ]
        reply = await llm._get_client().messages.create(
            model=model(),
            max_tokens=2000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in reply.content if b.type == "text")
        match = re.search(r"\{.*\}", text, re.S)
        parsed = json.loads(match.group(0)) if match else {"summary": text.strip()[:500]}
        return {
            "summary": str(parsed.get("summary", ""))[:600],
            "fixes": [
                {"issue": str(f.get("issue", ""))[:600], "fix": str(f.get("fix", ""))[:600]}
                for f in parsed.get("fixes", [])[:4]
                if isinstance(f, dict)
            ],
            "keep": [str(k)[:300] for k in parsed.get("keep", [])[:2]],
        }
    except Exception:  # comments are optional; the score stands without them
        logger.warning("Image eval comments failed for classifier %s", classifier_id, exc_info=True)
        return None
