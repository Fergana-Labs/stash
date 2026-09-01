"""From a folder of pages to the passages a voice is trained on.

Only prose teaches a voice. Headings, lists, tables, code, quotes and links
are structure or somebody else's words, so they are dropped before anything
is counted. What survives is grouped into passages of a few hundred words —
the unit the GPU job turns into training pairs — and judged against the
word gates the hosted product promises: 1,000 usable words to train, 2,000
recommended. This runs on every edit of the corpus, never on a GPU.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

MIN_WORDS = 1_000
RECOMMENDED_WORDS = 2_000

# A passage shorter than this is a caption or a stray line, not prose.
MIN_CHUNK_WORDS = 25
# Paragraphs are merged until a passage reaches this size, so an essay yields
# section-sized passages while a short email stays one short passage.
TARGET_CHUNK_WORDS = 300
MAX_CHUNK_WORDS = 600

SHORT_MAX_WORDS = 120
MEDIUM_MAX_WORDS = 500

_FENCE_RE = re.compile(r"(```|~~~).*?\1", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`)")
_STRUCTURE_LINE_RE = re.compile(
    r"^\s*("
    r"#{1,6}\s"  # heading
    r"|>"  # blockquote
    r"|\|"  # table row
    r"|[-*+]\s"  # bullet
    r"|\d+[.)]\s"  # numbered item
    r"|[-*_]{3,}\s*$"  # horizontal rule
    r"|[—–-]\s*@\w+"  # attribution footer an export appends ("— @handle · date")
    r")"
)


@dataclass(frozen=True)
class Document:
    name: str
    text: str


@dataclass(frozen=True)
class Chunk:
    text: str
    words: int
    length: str
    source: str


@dataclass
class CorpusReport:
    documents: int
    usable_documents: int
    raw_words: int
    usable_words: int
    chunks: list[Chunk]
    duplicate_chunks: int
    duplicate_words: int
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.reasons

    @property
    def status(self) -> str:
        if self.reasons:
            return "blocked"
        if self.warnings:
            return "warning"
        return "ready"

    def to_dict(self) -> dict:
        """The report without the passages themselves — what a person or an
        agent reads back. The passages go to the GPU, not to the caller."""
        data = asdict(self)
        data.pop("chunks")
        data["chunks"] = len(self.chunks)
        data["ready"] = self.ready
        data["status"] = self.status
        data["minimum_words"] = MIN_WORDS
        data["recommended_words"] = RECOMMENDED_WORDS
        return data


def _length_label(words: int) -> str:
    if words <= SHORT_MAX_WORDS:
        return "short"
    if words <= MEDIUM_MAX_WORDS:
        return "medium"
    return "long"


def _clean_inline(line: str) -> str:
    line = _IMAGE_RE.sub("", line)
    line = _LINK_RE.sub(r"\1", line)
    line = _URL_RE.sub("", line)
    line = _EMPHASIS_RE.sub("", line)
    return " ".join(line.split())


def paragraphs(text: str) -> list[str]:
    """The prose paragraphs of one document, structure removed."""
    text = _FENCE_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    out: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            if current:
                out.append(" ".join(current))
                current = []
            continue
        if _STRUCTURE_LINE_RE.match(raw):
            continue
        cleaned = _clean_inline(raw)
        if cleaned:
            current.append(cleaned)
    if current:
        out.append(" ".join(current))
    return out


def _split_long(words: list[str]) -> list[list[str]]:
    return [words[i : i + MAX_CHUNK_WORDS] for i in range(0, len(words), MAX_CHUNK_WORDS)]


def chunks_for(document: Document) -> list[Chunk]:
    """Merge a document's paragraphs into passages of a few hundred words."""
    out: list[Chunk] = []
    pending: list[str] = []

    def flush() -> None:
        if not pending:
            return
        words = " ".join(pending).split()
        pending.clear()
        for piece in _split_long(words):
            if len(piece) < MIN_CHUNK_WORDS:
                continue
            out.append(
                Chunk(
                    text=" ".join(piece),
                    words=len(piece),
                    length=_length_label(len(piece)),
                    source=document.name,
                )
            )

    for paragraph in paragraphs(document.text):
        pending.append(paragraph)
        if sum(len(p.split()) for p in pending) >= TARGET_CHUNK_WORDS:
            flush()
    flush()
    return out


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def inspect(documents: list[Document]) -> CorpusReport:
    raw_words = sum(len(d.text.split()) for d in documents)
    chunks: list[Chunk] = []
    usable_documents = 0
    for document in documents:
        found = chunks_for(document)
        if found:
            usable_documents += 1
        chunks.extend(found)

    seen: set[str] = set()
    unique: list[Chunk] = []
    duplicate_chunks = 0
    duplicate_words = 0
    for chunk in chunks:
        key = _normalized(chunk.text)
        if key in seen:
            duplicate_chunks += 1
            duplicate_words += chunk.words
            continue
        seen.add(key)
        unique.append(chunk)

    usable_words = sum(c.words for c in unique)
    report = CorpusReport(
        documents=len(documents),
        usable_documents=usable_documents,
        raw_words=raw_words,
        usable_words=usable_words,
        chunks=unique,
        duplicate_chunks=duplicate_chunks,
        duplicate_words=duplicate_words,
    )

    if not documents:
        report.reasons.append("The folder has no pages. Add the writing to train on first.")
    elif usable_words < MIN_WORDS:
        report.reasons.append(
            f"{usable_words:,} usable words; at least {MIN_WORDS:,} are needed. "
            "Headings, lists, tables, quotes and code don't count — only paragraphs of prose."
        )
    elif usable_words < RECOMMENDED_WORDS:
        report.warnings.append(
            f"{usable_words:,} usable words is enough, but {RECOMMENDED_WORDS:,}+ usually "
            "gives a stronger voice."
        )

    skipped = len(documents) - usable_documents
    if documents and skipped:
        report.warnings.append(
            f"{skipped} page{'s' if skipped != 1 else ''} had no usable prose and will be ignored."
        )
    if duplicate_chunks:
        report.warnings.append(
            f"Removed {duplicate_chunks} duplicate passage"
            f"{'s' if duplicate_chunks != 1 else ''} totaling {duplicate_words:,} words."
        )
    return report
