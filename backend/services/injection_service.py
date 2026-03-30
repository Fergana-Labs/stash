"""Injection scoring service: four-factor scoring with greedy knapsack budget filling.

Ported from replicate_me's injection engine. Scores candidates on:
  injection_score = relevance x recency x staleness x confidence

Candidate sources: always-inject notes, keyword-matched notes/patterns,
vector-similar events, FTS-matched events.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from ..database import get_pool
from . import embedding_service, memory_service, notebook_service


# --- Dataclasses ---


@dataclass
class InjectionCandidate:
    """A single item that could be injected into context."""

    key: str
    content: str
    section_header: str
    relevance: float = 1.0
    recency: float = 1.0
    staleness: float = 1.0
    confidence: float = 0.5
    token_cost: int = 0
    injection_score: float = 0.0
    source_type: str = "note"  # note, pattern, episode

    def compute_score(self) -> float:
        self.injection_score = self.relevance * self.recency * self.staleness * self.confidence
        return self.injection_score


@dataclass
class ItemState:
    last_injected_prompt: int = 0
    last_injected_ts: str = ""
    token_cost: int = 0


@dataclass
class SessionState:
    prompt_num: int = 0
    session_start: str = ""
    items: dict[str, ItemState] = field(default_factory=dict)


# --- Scoring functions (ported from replicate_me/memory/injection.py) ---


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def recency_score(
    inject_count: int,
    last_injected_at: datetime | None,
    now: datetime,
    intervals: list[float] | None = None,
) -> float:
    """Cross-session spaced repetition score."""
    if last_injected_at is None:
        return 1.0
    if intervals is None:
        intervals = [1.0, 4.0, 24.0, 72.0, 168.0, 720.0]

    hours_since = max((now - last_injected_at).total_seconds() / 3600.0, 0)
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
    """Within-session staleness. Higher = more stale = more likely to re-inject."""
    prompts_since = max(prompts_since, 0)
    decay_rate = decay_fast if avg_prompt_gap_seconds < fast_threshold else decay_slow
    prompt_decay = 1.0 - math.exp(-decay_rate * prompts_since)
    time_decay = 1.0 - math.exp(-2.0 * hours_since) if hours_since > 0 else 0.0
    return max(prompt_decay, time_decay)


def compute_confidence(outcomes: dict, floor: float = 0.15, ceiling: float = 0.95) -> float:
    """Outcome-based confidence for pattern cards."""
    total = sum(outcomes.values())
    if total == 0:
        return 0.5
    success_rate = (outcomes.get("success", 0) + 0.5 * outcomes.get("partial", 0)) / total
    return max(floor, min(ceiling, success_rate))


def select_injections(
    candidates: list[InjectionCandidate],
    budget_tokens: int,
    min_score: float = 0.01,
) -> list[InjectionCandidate]:
    """Greedy knapsack: sort by score, fill token budget."""
    for c in candidates:
        if c.token_cost == 0:
            c.token_cost = _estimate_tokens(c.content)
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


# --- Session state helpers ---


def _compute_staleness(
    key: str,
    session_state: SessionState,
    prompt_num: int,
    now: datetime,
    avg_gap: float,
    fast_threshold: float,
    decay_fast: float,
    decay_slow: float,
) -> float:
    item_state = session_state.items.get(key)
    if item_state is None:
        return 1.0

    prompts_since = prompt_num - item_state.last_injected_prompt
    hours_since = 0.0
    if item_state.last_injected_ts:
        try:
            last_ts = datetime.fromisoformat(item_state.last_injected_ts)
            hours_since = (now - last_ts).total_seconds() / 3600.0
        except ValueError:
            pass

    return staleness_score(
        prompts_since, hours_since, avg_gap,
        fast_threshold, decay_fast, decay_slow,
    )


# --- Config loading ---


async def _load_injection_config(agent_id: UUID) -> dict:
    """Load injection config for agent, or return defaults."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT budget_tokens, min_score, recency_intervals, "
        "staleness_decay_fast, staleness_decay_slow, staleness_fast_threshold_seconds "
        "FROM injection_configs WHERE agent_id = $1",
        agent_id,
    )
    if row:
        return dict(row)
    return {
        "budget_tokens": 4000,
        "min_score": 0.01,
        "recency_intervals": [1.0, 4.0, 24.0, 72.0, 168.0, 720.0],
        "staleness_decay_fast": 0.15,
        "staleness_decay_slow": 0.40,
        "staleness_fast_threshold_seconds": 60.0,
    }


# --- Main injection computation ---


async def compute_injection(
    agent_id: UUID,
    notebook_id: UUID,
    history_id: UUID,
    prompt_text: str,
    session_state_data: dict,
    session_id: str | None = None,
) -> dict:
    """Compute injection context using four-factor scoring.

    Returns: {context, updated_session_state, injected_items, total_tokens_used, budget_tokens}
    """
    cfg = await _load_injection_config(agent_id)
    now = datetime.now()

    # Parse session state
    session_state = SessionState(
        prompt_num=session_state_data.get("prompt_num", 0),
        session_start=session_state_data.get("session_start", now.isoformat()),
    )
    for key, item_data in session_state_data.get("items", {}).items():
        session_state.items[key] = ItemState(
            last_injected_prompt=item_data.get("last_injected_prompt", 0),
            last_injected_ts=item_data.get("last_injected_ts", ""),
            token_cost=item_data.get("token_cost", 0),
        )

    prompt_num = session_state.prompt_num
    try:
        session_start = datetime.fromisoformat(session_state.session_start)
    except ValueError:
        session_start = now
    elapsed = (now - session_start).total_seconds()
    avg_gap = elapsed / max(prompt_num, 1)

    budget = cfg["budget_tokens"]
    min_score = cfg["min_score"]
    recency_intervals = cfg["recency_intervals"]
    decay_fast = cfg["staleness_decay_fast"]
    decay_slow = cfg["staleness_decay_slow"]
    fast_threshold = cfg["staleness_fast_threshold_seconds"]

    candidates: list[InjectionCandidate] = []

    # --- Always-inject notebook pages ---
    always_pages = await notebook_service.get_always_inject_pages(notebook_id)
    for page in always_pages:
        meta = page.get("metadata", {})
        content = f"## {page['name']}\n{page['content_markdown']}"
        page_key = f"page:{page['id']}"

        inject_count = meta.get("inject_count", 0)
        last_inj_str = meta.get("last_injected_at")
        last_inj = datetime.fromisoformat(last_inj_str) if last_inj_str else None

        candidates.append(InjectionCandidate(
            key=page_key,
            content=content,
            section_header=page["name"],
            relevance=1.0,
            recency=recency_score(inject_count, last_inj, now, recency_intervals),
            staleness=_compute_staleness(
                page_key, session_state, prompt_num, now,
                avg_gap, fast_threshold, decay_fast, decay_slow,
            ),
            confidence=1.0,
            source_type="note",
        ))

    # --- Keyword-matched notebook pages ---
    if prompt_text:
        matched_pages = await notebook_service.search_pages_fts(notebook_id, prompt_text, limit=10)
        for page in matched_pages:
            page_key = f"page:{page['id']}"
            # Skip already-added always-inject pages
            if any(c.key == page_key for c in candidates):
                continue

            meta = page.get("metadata", {})
            content = f"## {page['name']}\n{page['content_markdown']}"

            inject_count = meta.get("inject_count", 0)
            last_inj_str = meta.get("last_injected_at")
            last_inj = datetime.fromisoformat(last_inj_str) if last_inj_str else None

            # Confidence: pattern cards use outcome-based, notes use 1.0
            note_type = meta.get("note_type", "note")
            if note_type == "pattern":
                confidence = compute_confidence(meta.get("outcomes", {}))
            else:
                confidence = 1.0

            fts_rank = page.get("rank", 0.5)
            candidates.append(InjectionCandidate(
                key=page_key,
                content=content,
                section_header=page["name"],
                relevance=min(fts_rank, 1.0),
                recency=recency_score(inject_count, last_inj, now, recency_intervals),
                staleness=_compute_staleness(
                    page_key, session_state, prompt_num, now,
                    avg_gap, fast_threshold, decay_fast, decay_slow,
                ),
                confidence=confidence,
                source_type="pattern" if note_type == "pattern" else "note",
            ))

    # --- Vector-similar history events ---
    if prompt_text and embedding_service.is_configured():
        query_vec = await embedding_service.embed_text(prompt_text)
        if query_vec is not None:
            vector_results = await memory_service.search_events_vector(
                history_id, query_vec, limit=15,
            )
            for evt in vector_results[:10]:
                evt_key = f"event:{evt['id']}"
                similarity = evt.get("similarity", 0.5)
                content = f"[{evt['event_type']}] {evt['content'][:300]}"

                candidates.append(InjectionCandidate(
                    key=evt_key,
                    content=content,
                    section_header="Relevant Past Experience",
                    relevance=max(similarity, 0.0),
                    recency=1.0,  # events don't track cross-session injection count
                    staleness=_compute_staleness(
                        evt_key, session_state, prompt_num, now,
                        avg_gap, fast_threshold, decay_fast, decay_slow,
                    ),
                    confidence=0.5,
                    source_type="episode",
                ))

    # --- FTS-matched history events ---
    if prompt_text:
        fts_results = await memory_service.search_events(history_id, prompt_text, limit=10)
        for evt in fts_results:
            evt_key = f"event:{evt['id']}"
            # Skip if already added via vector search
            if any(c.key == evt_key for c in candidates):
                continue

            content = f"[{evt['event_type']}] {evt['content'][:300]}"
            fts_rank = evt.get("rank", 0.3)

            candidates.append(InjectionCandidate(
                key=evt_key,
                content=content,
                section_header="Relevant Past Experience",
                relevance=min(fts_rank, 1.0),
                recency=1.0,
                staleness=_compute_staleness(
                    evt_key, session_state, prompt_num, now,
                    avg_gap, fast_threshold, decay_fast, decay_slow,
                ),
                confidence=0.5,
                source_type="episode",
            ))

    # --- Greedy knapsack selection ---
    selected = select_injections(candidates, budget, min_score)

    # --- Build context string ---
    sections: list[str] = []
    section_groups: dict[str, list[str]] = {}
    for c in selected:
        if c.source_type == "episode":
            section_groups.setdefault(c.section_header, []).append(c.content)
        else:
            sections.append(c.content)

    for header, items in section_groups.items():
        block = "\n".join(items)
        sections.append(f"## {header}\n{block}")

    context = "\n\n".join(sections)

    # --- Update session state ---
    now_iso = now.isoformat()
    new_prompt_num = prompt_num + 1
    for c in selected:
        session_state.items[c.key] = ItemState(
            last_injected_prompt=new_prompt_num,
            last_injected_ts=now_iso,
            token_cost=c.token_cost,
        )

    # Cap session state items at 200
    if len(session_state.items) > 200:
        sorted_items = sorted(
            session_state.items.items(),
            key=lambda kv: kv[1].last_injected_prompt,
        )
        session_state.items = dict(sorted_items[-200:])

    updated_state = {
        "prompt_num": new_prompt_num,
        "session_start": session_state.session_start,
        "items": {
            k: {
                "last_injected_prompt": v.last_injected_prompt,
                "last_injected_ts": v.last_injected_ts,
                "token_cost": v.token_cost,
            }
            for k, v in session_state.items.items()
        },
    }

    injected_items = [
        {
            "key": c.key,
            "source_type": c.source_type,
            "score": round(c.injection_score, 4),
            "token_cost": c.token_cost,
        }
        for c in selected
    ]

    total_tokens = sum(c.token_cost for c in selected)

    # --- Update notebook page injection metadata for injected pages ---
    for c in selected:
        if c.key.startswith("page:"):
            page_id = UUID(c.key.split(":", 1)[1])
            await notebook_service.update_page_injection_metadata(
                page_id, notebook_id, now_iso,
            )

    # --- Record injection session for outcome scoring ---
    if session_id:
        pattern_items = [
            {"key": c.key, "source_type": c.source_type, "score": round(c.injection_score, 4)}
            for c in selected if c.source_type == "pattern"
        ]
        if pattern_items:
            pool = get_pool()
            await pool.execute(
                "INSERT INTO injection_sessions (agent_id, session_id, injected_items) "
                "VALUES ($1, $2, $3::jsonb) "
                "ON CONFLICT (agent_id, session_id) DO UPDATE "
                "SET injected_items = $3::jsonb",
                agent_id, session_id, pattern_items,
            )

    return {
        "context": context,
        "updated_session_state": updated_state,
        "injected_items": injected_items,
        "total_tokens_used": total_tokens,
        "budget_tokens": budget,
    }
