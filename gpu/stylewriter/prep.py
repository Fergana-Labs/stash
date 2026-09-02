"""Turning passages into training pairs.

A passage alone teaches nothing about *responding to a brief*. So an
instruct model reads each passage and writes the notes its author might have
started from, and a flattened, generic rendering of it. Those become the
user turns; the person's real passage is always the assistant turn. The
instruct model is used here and only here — its own prose is what the
adapter is being trained away from.
"""

from __future__ import annotations

from .scaffold import rewrite_prompt, training_pair, write_prompt

NOTES_REQUEST = (
    "Here is a passage someone wrote.\n\n{passage}\n\n"
    "List the 3 to 6 factual points an author would have jotted down before writing it: "
    "names, claims, examples, numbers. One per line, each starting with '- '. "
    "Do not describe the style or structure. Notes only."
)

DEGRADE_REQUEST = (
    "Rewrite the following passage as plain, neutral, generic prose. Keep every fact, "
    "name and number; drop the personality, rhythm and phrasing. Output only the rewrite.\n\n"
    "{passage}"
)

# The continuation pair splits a passage here: the first part is context the
# model sees, the rest is what it learns to write next.
CONTINUE_SPLIT = 0.4
MIN_CONTINUE_WORDS = 80


def parse_notes(answer: str) -> list[str]:
    notes = []
    for line in answer.splitlines():
        line = line.strip()
        if line.startswith(("- ", "• ", "* ")):
            line = line[2:].strip()
        elif line[:2].rstrip(".)").isdigit():
            line = line.lstrip("0123456789.) ").strip()
        else:
            continue
        if line:
            notes.append(line)
    return notes[:6]


def split_for_continuation(text: str) -> tuple[str, str] | None:
    """(preceding, rest) at a sentence boundary near CONTINUE_SPLIT, or None
    when the passage is too short to split usefully."""
    words = text.split()
    if len(words) < MIN_CONTINUE_WORDS:
        return None
    target = int(len(words) * CONTINUE_SPLIT)
    head = " ".join(words[:target])
    cut = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if cut <= 0:
        return None
    return text[: cut + 1].strip(), text[cut + 1 :].strip()


def pairs_for_chunk(chunk: dict, notes: list[str], degraded: str) -> list[list[dict]]:
    """Every chat the adapter learns from one passage: write it from notes,
    continue it from its own opening, and rewrite a generic version of it."""
    text = chunk["text"]
    length = chunk["length"]
    pairs = [training_pair(write_prompt(notes, length), text)]
    split = split_for_continuation(text)
    if split is not None:
        preceding, rest = split
        pairs.append(training_pair(write_prompt(notes, length, preceding_text=preceding), rest))
    if degraded.strip():
        pairs.append(training_pair(rewrite_prompt(degraded), text))
    return pairs
