"""What a judge eval reads: an agent's trace and its output, as text and files.

Examples and scored calls share one shape, stored as JSON with files in object storage:

    {"name": str, "trace": [{"role", "content", "tool_name"?}], "text": str,
     "files": [{"key", "name", "content_type"}]}

Any part may be empty. Images are shown to the judge as pixels, PDFs as documents, and
text files inline; nothing is replaced by a description of it.
"""

import base64
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from .. import storage_service
from ..image_transcode import maybe_transcode_heic

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000
MAX_TRACE_STEPS = 200
TRACE_CHARS = 12_000
TEXT_CHARS = 8_000
FILE_TEXT_CHARS = 8_000
IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".csv",
    ".tsv",
    ".html",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".h",
    ".cpp",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".sh",
    ".diff",
    ".patch",
    ".log",
}


class Unreadable(ValueError):
    """A file the judge can't read; the caller sees the message."""


def _kind(name: str, content_type: str) -> str:
    if content_type == "application/pdf" or name.lower().endswith(".pdf"):
        return "pdf"
    if content_type.startswith("image/") or name.lower().endswith((".heic", ".heif")):
        return "image"
    if content_type.startswith("text/") or PurePosixPath(name.lower()).suffix in TEXT_SUFFIXES:
        return "text"
    return "other"


async def validate_file(name: str, data: bytes, content_type: str) -> tuple[str, bytes, str]:
    """(name, bytes, content_type) for a file the judge can read, or Unreadable."""
    content_type = (content_type or "").split(";")[0].strip().lower()
    if len(data) > MAX_FILE_BYTES:
        raise Unreadable(f"{name} is larger than 15 MB")
    kind = _kind(name, content_type)
    if kind == "image":
        data, name, content_type = await maybe_transcode_heic(data, name, content_type)
        try:
            with Image.open(BytesIO(data)) as image:
                fmt = IMAGE_TYPES.get(image.format or "")
                if not fmt or image.width * image.height > MAX_PIXELS:
                    raise Unreadable(f"{name} must be a PNG, JPEG, GIF or WEBP under 60 megapixels")
                image.verify()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise Unreadable(f"{name} is not a readable image") from exc
        return name, data, fmt
    if kind == "pdf":
        if not data.startswith(b"%PDF"):
            raise Unreadable(f"{name} is not a readable PDF")
        return name, data, "application/pdf"
    if kind == "text":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Unreadable(f"{name} is not UTF-8 text") from exc
        return name, data, content_type if content_type.startswith("text/") else "text/plain"
    raise Unreadable(f"{name}: use images, PDFs or text files")


def clean_trace(trace) -> list[dict]:
    """A trace as a list of steps; accepts a list of steps or plain text."""
    if not trace:
        return []
    if isinstance(trace, str):
        return [{"role": "trace", "content": trace}]
    if not isinstance(trace, list):
        raise ValueError("trace must be a list of steps or text")
    steps = []
    for step in trace[-MAX_TRACE_STEPS:]:
        if isinstance(step, str):
            steps.append({"role": "step", "content": step})
        elif isinstance(step, dict):
            content = step.get("content", step.get("text", ""))
            steps.append(
                {
                    "role": str(step.get("role", "step"))[:40],
                    "content": content if isinstance(content, str) else str(content),
                    **({"tool_name": str(step["tool_name"])[:80]} if step.get("tool_name") else {}),
                }
            )
    return steps


async def store(
    owner: UUID, name: str, files: list[tuple[str, bytes, str]], text: str = "", trace=None
) -> dict:
    """Validate and store an item's files; returns the item JSON."""
    checked = [await validate_file(n, d, c) for n, d, c in files]
    stored = []
    for n, d, c in checked:
        key = await storage_service.upload_file(str(owner), n or "file", d, c)
        stored.append({"key": key, "name": n[:300], "content_type": c})
    item = {
        "name": (name or "")[:300],
        "trace": clean_trace(trace),
        "text": (text or "")[:200_000],
        "files": stored,
    }
    if not item["text"] and not item["trace"] and not item["files"]:
        raise ValueError("Give the output as text, a trace, or files")
    return item


def _clip(text: str, limit: int, keep: str = "end") -> str:
    if len(text) <= limit:
        return text
    return ("…" + text[-limit:]) if keep == "end" else (text[:limit] + "…")


def _jpeg(data: bytes, side: int) -> dict:
    with Image.open(BytesIO(data)) as im:
        im = im.convert("RGB")
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


def closeup(data: bytes, side: int = 768) -> dict:
    """A full-resolution crop from the middle of an image, so line and texture are visible."""
    with Image.open(BytesIO(data)) as im:
        im = im.convert("RGB")
        w, h = im.size
        crop = min(w, h, 640)
        left, top = (w - crop) // 2, (h - crop) // 2
        im = im.crop((left, top, left + crop, top + crop))
        im.thumbnail((side, side))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=88)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.b64encode(buf.getvalue()).decode(),
        },
    }


async def blocks(item: dict, image_side: int = 768) -> list[dict]:
    """The item as Claude content blocks: trace and text as text, files as pixels/documents."""
    out: list[dict] = []
    if item.get("name"):
        out.append({"type": "text", "text": f"Name: {item['name']}"})
    if item.get("trace"):
        lines = "\n".join(
            f"[{s['role']}{' ' + s['tool_name'] if s.get('tool_name') else ''}] {s['content']}"
            for s in item["trace"]
        )
        out.append(
            {
                "type": "text",
                "text": "Agent trace (most recent last):\n" + _clip(lines, TRACE_CHARS),
            }
        )
    if item.get("text"):
        out.append(
            {"type": "text", "text": "Output:\n" + _clip(item["text"], TEXT_CHARS, keep="start")}
        )
    for f in item.get("files", []):
        data = await storage_service.download_file(f["key"])
        if f["content_type"].startswith("image/"):
            out += [{"type": "text", "text": f"Image: {f['name']}"}, _jpeg(data, image_side)]
        elif f["content_type"] == "application/pdf":
            out.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(data).decode(),
                    },
                    "title": f["name"][:200],
                }
            )
        else:
            out.append(
                {
                    "type": "text",
                    "text": f"File {f['name']}:\n"
                    + _clip(data.decode("utf-8", "replace"), FILE_TEXT_CHARS, keep="start"),
                }
            )
    return out


async def image_bytes(item: dict) -> list[bytes]:
    return [
        await storage_service.download_file(f["key"])
        for f in item.get("files", [])
        if f["content_type"].startswith("image/")
    ]
