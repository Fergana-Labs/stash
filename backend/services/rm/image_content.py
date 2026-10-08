"""Image references from native content blocks, without changing recorded text."""

import re
from dataclasses import dataclass


@dataclass
class TraceImage:
    start: int
    end: int
    data_url: str


def content_images(blocks, text: str) -> list[TraceImage]:
    if not isinstance(blocks, list):
        return []
    images = []
    offset = 0
    for block in blocks:
        if isinstance(block, str):
            value = block
        elif block.get("type") in ("text", "input_text", "output_text", "summary_text"):
            value = block["text"]
        else:
            value = f"[{block['type']}]"
        data_url = None
        if isinstance(block, dict):
            if block.get("type") in ("input_image", "image_url"):
                data_url = block.get("image_url")
                if isinstance(data_url, dict):
                    data_url = data_url.get("url")
            elif block.get("type") == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    data_url = f"data:{source.get('media_type')};base64,{source.get('data', '')}"
        if isinstance(data_url, str) and data_url.startswith("data:image/"):
            start, end = offset, offset + len(value)
            # Codex brackets attachments with a local-path tag. Replace that
            # entire wrapper visually; never open or fetch the referenced path.
            opening = re.search(r"<image\b[^>]*>\s*$", text[:start])
            closing = re.match(r"\s*</image>", text[end:])
            if opening and closing:
                start, end = opening.start(), end + closing.end()
            # DOM selections use UTF-16 offsets, including non-BMP characters.
            images.append(
                TraceImage(
                    len(text[:start].encode("utf-16-le")) // 2,
                    len(text[:end].encode("utf-16-le")) // 2,
                    data_url,
                )
            )
        offset += len(value) + 1  # _content_text joins blocks with newlines.
    return images
