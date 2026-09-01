"""The prompt format, shared by training and serving.

One rule drives the whole design: train on the user's prose in exactly the
format it will be generated in. Every training pair is a chat turn — an
instruction as the user message, a passage the person actually wrote as the
assistant message — and every draft is requested the same way. A mismatch
does not error; the prose just drifts back toward ordinary assistant
writing, which is why this module is the only place either side builds a
prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

LENGTHS = ("short", "medium", "long")

# Generation budget per length. The adapter learns to stop on its own; this
# is the ceiling, and a draft that hits it is trimmed to a sentence end.
MAX_TOKENS = {"short": 220, "medium": 700, "long": 1400}

LENGTH_WORDS = {"short": "a short passage", "medium": "a passage", "long": "a long passage"}

# Drawing several candidates needs variety without wandering off; these are
# the settings that kept detectors happy in trials on 14B instruct bases.
SAMPLING = {"temperature": 0.9, "top_p": 0.95, "repetition_penalty": 1.05}

SYSTEM = "You write in the author's own voice. Write only the passage."


@dataclass(frozen=True)
class Prompt:
    messages: list[dict]

    def to_dict(self) -> dict:
        return {"messages": self.messages}

    @classmethod
    def from_dict(cls, data: dict) -> Prompt:
        return cls(messages=list(data["messages"]))


def _notes_block(notes: list[str]) -> str:
    return "\n".join(f"- {note.strip()}" for note in notes if note.strip())


def write_prompt(notes: list[str], length: str, preceding_text: str = "") -> Prompt:
    """A fresh passage from notes, optionally continuing text already written.

    The notes are presented as material, never as instructions: the model
    is trained to write them up, not to obey them."""
    if length not in LENGTHS:
        raise ValueError(f"length must be one of {', '.join(LENGTHS)}")
    parts = [f"Write {LENGTH_WORDS[length]} covering these notes:", _notes_block(notes)]
    if not notes:
        parts = [f"Continue with {LENGTH_WORDS[length]}."]
    if preceding_text.strip():
        parts.append("It continues from this text:\n\n" + preceding_text.strip())
    return Prompt(
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "\n\n".join(p for p in parts if p)},
        ]
    )


def rewrite_prompt(text: str) -> Prompt:
    """The same content, in the author's voice."""
    return Prompt(
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": "Rewrite this in your own voice, keeping every fact:\n\n" + text.strip(),
            },
        ]
    )


def training_pair(prompt: Prompt, passage: str) -> list[dict]:
    """A full chat: the prompt and the passage the person actually wrote."""
    return [*prompt.messages, {"role": "assistant", "content": passage.strip()}]


def trim_to_sentence(text: str) -> str:
    """A draft cut off by the token ceiling ends mid-sentence; keep whole
    sentences only, unless that would leave nothing."""
    stripped = text.rstrip()
    last = max(stripped.rfind("."), stripped.rfind("!"), stripped.rfind("?"))
    if last <= 0:
        return stripped
    return stripped[: last + 1]
