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


def build_scored_local_context(
    db_path,
    agent_name: str,
    persona: str,
    prompt_text: str,
    session_state: dict,
    budget_tokens: int = 4000,
) -> str:
    """Build scored injection context from local SQLite DB.

    Uses FTS5 search + recent events as candidates, scores with four factors,
    and selects via greedy knapsack. Returns empty string if DB is unavailable.
    """
    try:
        import offline_db
        from pathlib import Path

        db = Path(db_path)
        if not db.exists():
            return ""

        offline_db.init_db(db)
        candidates: list[InjectionCandidate] = []

        # Identity header
        identity = f"## Agent Identity\nYou are **{agent_name}**, a Boozle agent."
        if persona:
            identity += f"\n{persona}"

        # FTS-matched events from prompt
        if prompt_text:
            fts_results = offline_db.search_events_fts(db, prompt_text, limit=20)
            for evt in fts_results:
                content = f"[{evt.get('event_type', '')}] {evt.get('content', '')[:300]}"
                candidates.append(InjectionCandidate(
                    key=f"event:{evt['id']}",
                    content=content,
                    section_header="Relevant Past Experience",
                    relevance=min(abs(evt.get("rank", 0.5)), 1.0),
                    recency=1.0,
                    confidence=0.5,
                    source_type="episode",
                ))

        # FTS-matched notebook pages
        if prompt_text:
            page_results = offline_db.search_pages_fts(db, prompt_text, limit=10)
            for page in page_results:
                meta = {}
                try:
                    meta = __import__("json").loads(page.get("metadata", "{}"))
                except Exception:
                    pass
                content = f"## {page.get('name', '')}\n{page.get('content_markdown', '')}"
                note_type = meta.get("note_type", "note")
                candidates.append(InjectionCandidate(
                    key=f"page:{page['id']}",
                    content=content,
                    section_header=page.get("name", ""),
                    relevance=min(abs(page.get("rank", 0.5)), 1.0),
                    recency=1.0,
                    confidence=1.0 if note_type != "pattern" else 0.5,
                    source_type="pattern" if note_type == "pattern" else "note",
                ))

        # Recent events for recency
        recent = offline_db.get_recent_events(db, limit=10)
        for evt in recent:
            evt_key = f"event:{evt['id']}"
            if any(c.key == evt_key for c in candidates):
                continue
            content = f"[{evt.get('event_type', '')}] {evt.get('content', '')[:200]}"
            candidates.append(InjectionCandidate(
                key=evt_key,
                content=content,
                section_header="Recent Activity",
                relevance=0.4,
                recency=1.0,
                confidence=0.5,
                source_type="episode",
            ))

        if not candidates:
            return ""

        # Select via scoring + knapsack
        selected = select_injections(candidates, budget_tokens)

        # Build context
        sections = [identity]
        section_groups: dict[str, list[str]] = {}
        for c in selected:
            if c.source_type == "episode":
                section_groups.setdefault(c.section_header, []).append(c.content)
            else:
                sections.append(c.content)

        for header, items in section_groups.items():
            sections.append(f"## {header}\n" + "\n".join(items))

        return "\n\n".join(sections)

    except Exception:
        return ""


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
