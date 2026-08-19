"""Repair Google-export damage in already-extracted Drive documents.

The extraction-time repair (repair_exported_frontmatter) only runs when a
document is re-extracted, and extraction is keyed on Drive's own modifiedTime —
so a document damaged before the repair shipped stays damaged until its author
happens to edit it. This carries the stored rows forward once.

The logic is a frozen copy of the frontmatter half of the extraction-time
repair (repair_exported_markdown), per this directory's convention: a migration
must keep producing the same result even after the live code moves on. The
body-unescape half is deliberately NOT backfilled: stored rows don't record
whether their text came from a Docs markdown export (where a backslash is the
exporter's) or a PDF/plain-file extraction (where it may be the author's), so
bodies heal on the document's next edit-driven re-extraction instead.

A row is rewritten only when the repair turns it into a valid skill declaration
it wasn't before, or when it already declared a skill whose values are wrapped
in the curly quotes only Docs' exporter produces. A document that already
declares a clean skill — e.g. a hand-authored SKILL.md synced from a Drive
folder — stays exactly as its author wrote it.

Revision ID: 0187
Revises: 0186
"""

import json
import re

from alembic import op
from sqlalchemy import text

revision = "0187"
down_revision = "0186"
branch_labels = None
depends_on = None

FRONTMATTER_SCAN_BYTES = 8192
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024

_ESCAPED_RULE_RE = re.compile(r"^\\(-{3,})[ \t]*$", re.MULTILINE)
_DELIMITER_RE = re.compile(r"\\?-{3,}[ \t]*")
_EMPHASIS_RE = re.compile(r"(?<!\\)[*_]+")
_MARKDOWN_ESCAPE_RE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")
_QUOTE_PAIRS = (("\u201c", "\u201d"), ("\u2018", "\u2019"), ('"', '"'))
_CURLY_PAIRS = (("\u201c", "\u201d"), ("\u2018", "\u2019"))


def _repair(markdown: str) -> str:
    text_ = _ESCAPED_RULE_RE.sub(r"\1", markdown)
    head, tail = text_[:FRONTMATTER_SCAN_BYTES], text_[FRONTMATTER_SCAN_BYTES:]
    repaired_head = _repaired_head(head)
    if repaired_head is None:
        return text_
    candidate = repaired_head + tail
    if not _declares_skill(candidate[:FRONTMATTER_SCAN_BYTES]):
        return text_
    return candidate


def _repaired_head(head: str) -> str | None:
    lines = head.lstrip("\ufeff").split("\n")
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or not _DELIMITER_RE.fullmatch(lines[start]):
        return None
    closing = next(
        (i for i in range(start + 1, len(lines)) if _DELIMITER_RE.fullmatch(lines[i])), None
    )
    if closing is None:
        return None
    repaired = [_repair_line(line) for line in lines[start + 1 : closing]]
    return "\n".join(["---", *repaired, "---", *lines[closing + 1 :]])


def _repair_line(line: str) -> str:
    line = _MARKDOWN_ESCAPE_RE.sub(r"\1", _EMPHASIS_RE.sub("", line))
    key, colon, value = line.partition(":")
    if not colon:
        return line
    value = value.strip()
    for opening, closing in _QUOTE_PAIRS:
        if len(value) >= 2 and value.startswith(opening) and value.endswith(closing):
            value = json.dumps(value[1:-1], ensure_ascii=False)
            break
    return f"{key.strip()}: {value}"


def _frontmatter(md: str) -> dict | None:
    if not md.startswith("---"):
        return None
    end = md.find("\n---", 3)
    if end == -1:
        return None
    meta: dict = {}
    for line in md[3:end].strip("\n").splitlines():
        line = line.rstrip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            try:
                val = str(json.loads(val))
            except ValueError:
                return None
        meta[key.strip()] = val
    return meta


def _declares_skill(md: str) -> bool:
    meta = _frontmatter(md)
    if meta is None:
        return False
    name = meta.get("name", "").strip()
    description = meta.get("description", "").strip()
    return (
        0 < len(name) <= MAX_SKILL_NAME_LENGTH
        and 0 < len(description) <= MAX_SKILL_DESCRIPTION_LENGTH
    )


def _curly_wrapped(meta: dict) -> bool:
    return any(
        len(value) >= 2 and value.startswith(opening) and value.endswith(closing)
        for value in meta.values()
        if isinstance(value, str)
        for opening, closing in _CURLY_PAIRS
    )


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        text(
            "SELECT id, content FROM drive_documents "
            "WHERE deleted_at IS NULL AND content IS NOT NULL "
            "  AND left(content, 64) LIKE '%---%'"
        )
    ).mappings()
    for row in rows:
        content = row["content"]
        repaired = _repair(content)
        if repaired == content:
            continue
        if not _declares_skill(repaired[:FRONTMATTER_SCAN_BYTES]):
            continue
        current = _frontmatter(content[:FRONTMATTER_SCAN_BYTES])
        already_a_skill = _declares_skill(content[:FRONTMATTER_SCAN_BYTES])
        if already_a_skill and not (current and _curly_wrapped(current)):
            continue
        bind.execute(
            text(
                "UPDATE drive_documents SET content = :content, "
                "content_hash = md5(:content), embed_stale = TRUE, updated_at = now() "
                "WHERE id = :row_id"
            ),
            {"content": repaired, "row_id": row["id"]},
        )


def downgrade() -> None:
    pass
