"""Pick a draft: the first batch that clears the detector, ranked by style.

A trained adapter usually clears the gate on its first or second candidate,
so the common case costs one small batch, not a fixed eight generations.
When nothing clears it within the cap, the closest candidate comes back
marked `soft_failed` so the caller can say so instead of shipping it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

BATCH = 4
CAP = 8
HUMAN_THRESHOLD = 0.5


@dataclass
class Candidate:
    text: str
    style: float
    p_human: float


@dataclass
class Chosen:
    text: str
    style: float
    p_human: float
    draws: int
    soft_failed: bool
    alternates: list[Candidate] = field(default_factory=list)


def best_of_n(
    draw: Callable[[int], list[str]],
    score: Callable[[str], float],
    detect: Callable[[list[str]], list[float]] | None,
    cap: int = CAP,
    batch: int = BATCH,
) -> Chosen:
    """`draw(n)` produces n texts; `score` is style similarity; `detect`
    maps texts to p_human (None disables the gate and ranks a single batch)."""
    seen: list[Candidate] = []
    draws = 0
    while draws < cap:
        count = min(batch, cap - draws)
        texts = [t for t in draw(count) if t.strip()]
        draws += count
        if not texts:
            continue
        readings = detect(texts) if detect else [1.0] * len(texts)
        seen.extend(Candidate(t, score(t), p) for t, p in zip(texts, readings, strict=True))
        passing = [c for c in seen if c.p_human >= HUMAN_THRESHOLD]
        if passing:
            return _choose(passing, seen, draws, soft_failed=False)
        if detect is None:
            break
    if not seen:
        raise RuntimeError("the model produced no text")
    return _choose(seen, seen, draws, soft_failed=True)


def _choose(pool: list[Candidate], seen: list[Candidate], draws: int, soft_failed: bool) -> Chosen:
    best = max(pool, key=lambda c: (c.style, c.p_human))
    return Chosen(
        text=best.text,
        style=best.style,
        p_human=best.p_human,
        draws=draws,
        soft_failed=soft_failed,
        alternates=sorted((c for c in seen if c is not best), key=lambda c: -c.style),
    )
