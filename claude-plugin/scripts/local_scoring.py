"""Local fallback scoring engine for offline injection.

Bundled subset of replicate_me's injection.py scoring functions.
Used when the Boozle API is unreachable. Keyword-only matching (no vector search).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class InjectionCandidate:
    key: str
    content: str
    section_header: str
    relevance: float = 1.0
    recency: float = 1.0
    staleness: float = 1.0
    confidence: float = 0.5
    token_cost: int = 0
    injection_score: float = 0.0
    source_type: str = "note"

    def compute_score(self) -> float:
        self.injection_score = self.relevance * self.recency * self.staleness * self.confidence
        return self.injection_score


def recency_score(
    inject_count: int,
    last_injected_at_hours: float | None,
    intervals: list[float] | None = None,
) -> float:
    if last_injected_at_hours is None:
        return 1.0
    if intervals is None:
        intervals = [1.0, 4.0, 24.0, 72.0, 168.0, 720.0]
    hours_since = max(last_injected_at_hours, 0)
    level = min(inject_count, len(intervals) - 1)
    optimal = intervals[level]
    ratio = hours_since / optimal if optimal > 0 else 1.0
    if ratio < 0.5:
        return 0.1
    elif ratio < 2.0:
        return 0.8 * math.exp(-2.0 * (ratio - 1.0) ** 2)
    else:
        return 0.4 * math.exp(-0.1 * (ratio - 2.0))


def staleness_score(
    prompts_since: int,
    hours_since: float,
    avg_prompt_gap_seconds: float,
    fast_threshold: float = 60.0,
    decay_fast: float = 0.15,
    decay_slow: float = 0.40,
) -> float:
    prompts_since = max(prompts_since, 0)
    decay_rate = decay_fast if avg_prompt_gap_seconds < fast_threshold else decay_slow
    prompt_decay = 1.0 - math.exp(-decay_rate * prompts_since)
    time_decay = 1.0 - math.exp(-2.0 * hours_since) if hours_since > 0 else 0.0
    return max(prompt_decay, time_decay)


def select_injections(
    candidates: list[InjectionCandidate],
    budget_tokens: int = 4000,
    min_score: float = 0.01,
) -> list[InjectionCandidate]:
    for c in candidates:
        if c.token_cost == 0:
            c.token_cost = len(c.content) // 4
        c.compute_score()

    viable = [c for c in candidates if c.injection_score >= min_score]
    viable.sort(key=lambda c: c.injection_score, reverse=True)

    selected: list[InjectionCandidate] = []
    remaining = budget_tokens
    for c in viable:
        if c.token_cost <= remaining:
            selected.append(c)
            remaining -= c.token_cost
        if remaining < 100:
            break
    return selected


def build_fallback_context(
    agent_name: str,
    persona: str,
    recent_events: list[dict],
) -> str:
    """Build a basic context string from cached data when API is unreachable."""
    lines = []
    lines.append(f"## Agent Identity")
    lines.append(f"You are **{agent_name}**, a Boozle agent.")
    if persona:
        lines.append(persona)
    lines.append("")

    if recent_events:
        lines.append("## Recent Activity (your previous sessions)")
        for event in recent_events[:15]:
            ts = event.get("created_at", "")[:16]
            tool = event.get("tool_name", "")
            content = event.get("content", "")[:200]
            event_type = event.get("event_type", "")
            if tool:
                lines.append(f"- [{ts}] {tool}: {content}")
            else:
                lines.append(f"- [{ts}] ({event_type}) {content}")
        lines.append("")

    return "\n".join(lines)
