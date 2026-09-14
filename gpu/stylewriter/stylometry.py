"""A small stylometric profile: does this text make the choices this author
makes? It is not an AI detector. It ranks candidates that already read as
human by how close they sit to the corpus, and it gives `score` something
honest to report after edits.

The features are the classic, cheap ones — sentence and word length, how
often the author reaches for commas, dashes, questions, contractions,
first person, and the most common function words — standardised against the
corpus so that no single feature dominates. Similarity is one minus a
bounded normalised distance, so 1.0 is "indistinguishable from the corpus"
and the author's own held-out writing typically lands around 0.5.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")
_WORD_RE = re.compile(r"[A-Za-z']+")
_CONTRACTION_RE = re.compile(r"\b\w+'(s|t|re|ve|ll|d|m)\b", re.IGNORECASE)

FUNCTION_WORDS = (
    "the", "and", "of", "to", "a", "in", "that", "is", "it", "i", "you", "for", "but",
    "not", "with", "this", "on", "was", "be", "are", "as", "have", "so", "just", "like",
    "because", "really", "very", "which", "what",
)  # fmt: skip

_MIN_STD = 1e-3


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]


def features(text: str) -> list[float]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    sentences = _sentences(text)
    n_words = max(len(words), 1)
    n_sentences = max(len(sentences), 1)
    lengths = [len(_WORD_RE.findall(s)) for s in sentences] or [0]
    mean_len = sum(lengths) / n_sentences
    var_len = sum((x - mean_len) ** 2 for x in lengths) / n_sentences
    per_word = {w: words.count(w) / n_words for w in FUNCTION_WORDS}
    return [
        mean_len,
        math.sqrt(var_len),
        sum(len(w) for w in words) / n_words,
        len(set(words)) / n_words,
        text.count(",") / n_sentences,
        (text.count(" - ") + text.count("—") + text.count("–")) / n_sentences,
        text.count("?") / n_sentences,
        text.count("!") / n_sentences,
        text.count(";") / n_sentences,
        text.count(":") / n_sentences,
        text.count("(") / n_sentences,
        len(_CONTRACTION_RE.findall(text)) / n_words,
        sum(1 for w in words if w in ("i", "me", "my", "mine", "myself")) / n_words,
        sum(1 for w in words if w in ("you", "your", "yours")) / n_words,
        sum(1 for w in words if w in ("we", "us", "our")) / n_words,
        sum(1 for w in words if len(w) >= 10) / n_words,
        *(per_word[w] for w in FUNCTION_WORDS),
    ]


@dataclass(frozen=True)
class Profile:
    mean: list[float]
    std: list[float]

    def to_dict(self) -> dict:
        return {"mean": self.mean, "std": self.std}

    @classmethod
    def from_dict(cls, data: dict) -> Profile:
        return cls(mean=list(data["mean"]), std=list(data["std"]))


def fit(texts: list[str]) -> Profile:
    if not texts:
        raise ValueError("cannot fit a profile on no text")
    rows = [features(t) for t in texts]
    n = len(rows)
    dims = len(rows[0])
    mean = [sum(r[i] for r in rows) / n for i in range(dims)]
    std = [
        max(math.sqrt(sum((r[i] - mean[i]) ** 2 for r in rows) / n), _MIN_STD) for i in range(dims)
    ]
    return Profile(mean=mean, std=std)


def similarity(profile: Profile, text: str) -> float:
    """1.0 at the corpus centre, falling toward 0 as the text's choices drift.
    Distances are in standard deviations of the corpus, averaged over
    features, and squashed so one wild feature cannot zero the score."""
    if not text.strip():
        return 0.0
    row = features(text)
    z = [abs(row[i] - profile.mean[i]) / profile.std[i] for i in range(len(row))]
    mean_z = sum(min(v, 6.0) for v in z) / len(z)
    return round(1.0 / (1.0 + mean_z), 4)
