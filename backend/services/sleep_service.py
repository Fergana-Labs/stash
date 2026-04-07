"""Sleep agent service: server-side periodic curation per agent.

Reads from history_events (PostgreSQL), curates notebook_pages (pattern cards,
monologues), scores outcomes for injected patterns, and manages sleep watermarks.

Ported from replicate_me's local sleep agent (memory/sleep.py + llm.py).
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import UUID

import anthropic

from ..database import get_pool
from . import memory_service, notebook_service

logger = logging.getLogger(__name__)

_anthropic: anthropic.AsyncAnthropic | None = None


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.AsyncAnthropic()
    return _anthropic


# --- Config loading ---


async def _load_sleep_config(agent_id: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT enabled, interval_minutes, max_pattern_cards, monologue_batch_size, "
        "monologue_model, curation_model, curation_sources, curation_rules, workspace_ids "
        "FROM sleep_configs WHERE persona_id = $1",
        agent_id,
    )
    if row:
        return dict(row)
    return {
        "enabled": True,
        "interval_minutes": 60,
        "max_pattern_cards": 500,
        "monologue_batch_size": 20,
        "monologue_model": "claude-haiku-4-5-20251001",
        "curation_model": "claude-haiku-4-5-20251001",
        "curation_sources": ["history"],
        "curation_rules": {},
        "workspace_ids": [],
    }


# --- Watermark management ---


async def _get_watermark(agent_id: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT last_event_at, last_monologue_event_at, last_run_at "
        "FROM sleep_watermarks WHERE persona_id = $1",
        agent_id,
    )
    if row:
        return dict(row)
    return {"last_event_at": None, "last_monologue_event_at": None, "last_run_at": None}


async def _set_watermark(agent_id: UUID, last_event_at: datetime, last_monologue_event_at: datetime | None = None) -> None:
    pool = get_pool()
    await pool.execute(
        "INSERT INTO sleep_watermarks (persona_id, last_event_at, last_monologue_event_at, last_run_at, updated_at) "
        "VALUES ($1, $2, $3, now(), now()) "
        "ON CONFLICT (persona_id) DO UPDATE SET "
        "last_event_at = $2, last_run_at = now(), updated_at = now()"
        + (", last_monologue_event_at = $3" if last_monologue_event_at else ""),
        agent_id, last_event_at, last_monologue_event_at,
    )


# --- Persona resource lookup ---


async def _get_persona_resources(persona_id: UUID) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT notebook_id, history_id FROM users WHERE id = $1 AND type = 'persona'",
        persona_id,
    )
    if not row or not row["notebook_id"] or not row["history_id"]:
        raise ValueError(f"Persona {persona_id} has no provisioned notebook or history")
    return dict(row)


# --- Episode gathering ---


async def _get_episodes_since(history_id: UUID, after_ts: datetime | None, limit: int = 500) -> list[dict]:
    """Get events since watermark timestamp."""
    pool = get_pool()
    if after_ts:
        rows = await pool.fetch(
            "SELECT id, store_id, agent_name, event_type, session_id, tool_name, "
            "content, metadata, created_at "
            "FROM history_events WHERE store_id = $1 AND created_at > $2 "
            "ORDER BY created_at ASC LIMIT $3",
            history_id, after_ts, limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT id, store_id, agent_name, event_type, session_id, tool_name, "
            "content, metadata, created_at "
            "FROM history_events WHERE store_id = $1 "
            "ORDER BY created_at ASC LIMIT $2",
            history_id, limit,
        )
    return [dict(r) for r in rows]


# --- Health detection (pure heuristics, no LLM) ---


def _detect_health_issues(episodes: list[dict]) -> dict:
    issues: dict = {}

    if len(episodes) >= 10:
        recent = episodes[-30:]
        tool_counts = Counter(
            (ep.get("tool_name") or "none") for ep in recent if ep.get("event_type") == "tool_use"
        )
        for tool, count in tool_counts.items():
            if count >= 5:
                issues["loops_detected"] = True
                issues["loop_tool"] = tool
                break

    tool_events = [ep for ep in episodes if ep.get("event_type") == "tool_use"]
    if tool_events:
        error_count = sum(
            1 for ep in tool_events
            if isinstance(ep.get("metadata"), dict) and (ep["metadata"].get("error") or ep["metadata"].get("is_error"))
        )
        if len(tool_events) > 5 and error_count / len(tool_events) > 0.5:
            issues["high_error_rate"] = True
            issues["error_rate"] = round(error_count / len(tool_events), 2)

    now = datetime.now(timezone.utc)
    if episodes:
        last_ts = episodes[-1].get("created_at")
        if last_ts and isinstance(last_ts, datetime):
            if (now - last_ts) > timedelta(minutes=30):
                issues["stalled"] = True

    return issues


# --- Multi-source data gathering ---


async def _get_notebook_changes_since(
    workspace_ids: list[UUID], after_ts: datetime | None, limit: int = 100,
) -> list[dict]:
    """Get notebook pages updated since watermark across specified workspaces."""
    pool = get_pool()
    if not workspace_ids:
        return []
    if after_ts:
        rows = await pool.fetch(
            "SELECT np.id, np.name, np.content_markdown, np.updated_at, n.name AS notebook_name "
            "FROM notebook_pages np JOIN notebooks n ON n.id = np.notebook_id "
            "WHERE n.workspace_id = ANY($1) AND np.updated_at > $2 "
            "ORDER BY np.updated_at ASC LIMIT $3",
            workspace_ids, after_ts, limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT np.id, np.name, np.content_markdown, np.updated_at, n.name AS notebook_name "
            "FROM notebook_pages np JOIN notebooks n ON n.id = np.notebook_id "
            "WHERE n.workspace_id = ANY($1) "
            "ORDER BY np.updated_at DESC LIMIT $2",
            workspace_ids, limit,
        )
    return [dict(r) for r in rows]


async def _get_new_documents(workspace_ids: list[UUID], after_ts: datetime | None) -> list[dict]:
    """Get documents that became ready since watermark across workspaces."""
    pool = get_pool()
    if not workspace_ids:
        return []
    if after_ts:
        rows = await pool.fetch(
            "SELECT id, workspace_id, name, file_type, metadata, updated_at "
            "FROM documents WHERE workspace_id = ANY($1) AND status = 'ready' "
            "AND updated_at > $2 ORDER BY updated_at ASC",
            workspace_ids, after_ts,
        )
    else:
        rows = await pool.fetch(
            "SELECT id, workspace_id, name, file_type, metadata, updated_at "
            "FROM documents WHERE workspace_id = ANY($1) AND status = 'ready' "
            "ORDER BY updated_at DESC LIMIT 20",
            workspace_ids,
        )
    return [dict(r) for r in rows]


async def _get_table_changes_since(
    workspace_ids: list[UUID], after_ts: datetime | None, limit: int = 100,
) -> list[dict]:
    """Get table rows updated since watermark across workspaces."""
    pool = get_pool()
    if not workspace_ids:
        return []
    if after_ts:
        rows = await pool.fetch(
            "SELECT tr.id, tr.data, tr.updated_at, t.name AS table_name "
            "FROM table_rows tr JOIN tables t ON t.id = tr.table_id "
            "WHERE t.workspace_id = ANY($1) AND tr.updated_at > $2 "
            "ORDER BY tr.updated_at ASC LIMIT $3",
            workspace_ids, after_ts, limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT tr.id, tr.data, tr.updated_at, t.name AS table_name "
            "FROM table_rows tr JOIN tables t ON t.id = tr.table_id "
            "WHERE t.workspace_id = ANY($1) "
            "ORDER BY tr.updated_at DESC LIMIT $2",
            workspace_ids, limit,
        )
    return [dict(r) for r in rows]


async def _get_workspace_history_since(
    workspace_ids: list[UUID], after_ts: datetime | None, limit: int = 200,
) -> list[dict]:
    """Get history events from workspace stores since watermark."""
    pool = get_pool()
    if not workspace_ids:
        return []
    if after_ts:
        rows = await pool.fetch(
            "SELECT he.id, he.agent_name, he.event_type, he.content, he.created_at, "
            "h.name AS store_name "
            "FROM history_events he JOIN histories h ON h.id = he.store_id "
            "WHERE h.workspace_id = ANY($1) AND he.created_at > $2 "
            "ORDER BY he.created_at ASC LIMIT $3",
            workspace_ids, after_ts, limit,
        )
    else:
        rows = await pool.fetch(
            "SELECT he.id, he.agent_name, he.event_type, he.content, he.created_at, "
            "h.name AS store_name "
            "FROM history_events he JOIN histories h ON h.id = he.store_id "
            "WHERE h.workspace_id = ANY($1) "
            "ORDER BY he.created_at DESC LIMIT $2",
            workspace_ids, limit,
        )
    return [dict(r) for r in rows]


def _format_notebook_changes_for_llm(changes: list[dict]) -> str:
    if not changes:
        return "(no notebook changes)"
    lines = []
    for c in changes[:50]:
        content_preview = (c.get("content_markdown") or "")[:200]
        lines.append(f"[{c.get('notebook_name', '?')}/{c['name']}] {content_preview}")
    return "\n".join(lines)


def _format_documents_for_llm(docs: list[dict]) -> str:
    if not docs:
        return "(no new documents)"
    lines = []
    for d in docs:
        meta = d.get("metadata", {})
        chunks = meta.get("chunk_count", "?")
        lines.append(f"[{d['name']}] type={d['file_type']} chunks={chunks}")
    return "\n".join(lines)


def _format_table_changes_for_llm(changes: list[dict]) -> str:
    if not changes:
        return "(no table changes)"
    lines = []
    for c in changes[:50]:
        data_preview = str(c.get("data", {}))[:200]
        lines.append(f"[{c.get('table_name', '?')}] {data_preview}")
    return "\n".join(lines)


# --- Formatting helpers ---


def _format_episodes_for_llm(episodes: list[dict]) -> str:
    lines = []
    for ep in episodes[-100:]:
        line = f"[{ep.get('created_at', '')}] {ep.get('event_type', '')}"
        tool = ep.get("tool_name")
        if tool:
            line += f" ({tool})"
        content = ep.get("content", "")
        if content:
            line += f": {content[:100]}"
        lines.append(line)
    return "\n".join(lines)


def _format_notes_for_llm(pages: list[dict]) -> str:
    # Group by category for LLM context
    categories: dict[str, list[dict]] = {}
    uncategorized: list[dict] = []
    for page in pages:
        meta = page.get("metadata", {})
        cat = meta.get("category", "")
        if cat:
            categories.setdefault(cat, []).append(page)
        else:
            uncategorized.append(page)

    lines = []
    if categories:
        lines.append("### Categories")
        for cat_name, cat_pages in sorted(categories.items()):
            lines.append(f"\n**{cat_name}** ({len(cat_pages)} pages):")
            for page in cat_pages:
                meta = page.get("metadata", {})
                note_type = meta.get("note_type", "note")
                lines.append(f"  - {page['id']} [{note_type}]: {page['name']}")

    if uncategorized:
        lines.append("\n### Uncategorized")
        for page in uncategorized:
            meta = page.get("metadata", {})
            note_type = meta.get("note_type", "note")
            importance = meta.get("importance", 0.5)
            keywords = ", ".join(meta.get("keywords", []))
            preview = page.get("content_markdown", "")[:150]
            lines.append(
                f"- {page['id']} [{note_type}] (importance: {importance}): "
                f"{page['name']} — keywords: {keywords}\n  {preview}"
            )

    return "\n".join(lines) if lines else "(no notes yet — create categories and notes)"


# --- LLM calls ---


async def _generate_monologue_text(model: str, episodes: list[dict]) -> str:
    formatted = "\n".join(
        f"[{e.get('created_at', '')}] {e.get('event_type', '')}"
        + (f" ({e.get('tool_name')})" if e.get("tool_name") else "")
        + f": {e.get('content', '')[:200]}"
        for e in episodes
    )
    client = _get_anthropic()
    response = await client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "Summarize the following sequence of events from a coding session "
                "into a brief narrative monologue (2-4 sentences). Focus on what "
                "was accomplished, what decisions were made, and any patterns observed.\n\n"
                f"Events:\n{formatted}\n\nMonologue:"
            ),
        }],
    )
    return response.content[0].text.strip()


async def _score_outcomes_llm(model: str, session_summary: str, injected_cards: list[dict]) -> list[dict]:
    cards_text = "\n".join(
        f"- {c['page_id']}: {c['name']} — {c['preview']}"
        for c in injected_cards
    )
    prompt = f"""You are scoring whether injected advice cards were useful in a coding session.

## Session Summary
{session_summary}

## Injected Cards
{cards_text}

## Verdict Options
- **success**: User followed the advice, good outcome
- **partial**: Advice was relevant but only partly used
- **irrelevant**: Card matched keywords but session had nothing to do with it
- **override**: User explicitly did the opposite
- **failure**: Advice was wrong or led to problems

For each card, respond with a JSON array of objects:
[{{"page_id": "...", "verdict": "..."}}]

Respond ONLY with valid JSON."""

    client = _get_anthropic()
    response = await client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


async def _llm_curate(model: str, episodes_summary: str, notes_summary: str, since_last: str) -> dict:
    prompt = f"""You are a knowledge base curator. Your job is to organize incoming information
into a structured wiki with categories, topic pages, and cross-linked content.

## Current Wiki Pages
{notes_summary}

## New Content (since last curation: {since_last})
{episodes_summary}

## Instructions
Analyze the new content and produce a JSON response with these actions:

1. "create_notes": [{{
     "title": str,
     "keywords": [str],
     "content": str,              # Markdown content. Use [[Page Title]] wiki links to reference other pages.
     "importance": float,          # 0-1 scale
     "type": "note"|"pattern"|"category",
     "category": str,             # Category name this belongs to (e.g., "Machine Learning", "Web Development")
     "folder": str                # Folder name to file this under (same as category usually)
   }}]
   - type "category": Create a category index page. Title should be the category name.
     Content should list and link to all known pages in that category using [[wiki links]].
   - type "note": A knowledge page about a specific topic. Link to its category page.
   - type "pattern": A recurring pattern. Include "situation", "lessons" (list), "confidence" (0-1).

2. "update_notes": [{{
     "page_id": str,
     "content_additions": str,    # Append to existing content
     "keywords": [str],           # Replaces keyword list (omit to leave unchanged)
     "importance": float
   }}]

3. "merge_notes": [{{"source_page_ids": [str], "new_title": str, "category": str}}]

4. "delete_notes": [page_id strings]

5. "update_categories": [{{
     "page_id": str,              # ID of an existing category index page
     "add_links": [str]           # Page titles to add as [[wiki links]] to the category
   }}]

6. "health": {{"loops_detected": bool, "stuck": bool, "recommend_restart": bool, "message": "optional"}}

## Guidelines
- **Categorize everything.** Every note should belong to a category. If a category page doesn't exist, create one.
- **Use [[wiki links]]** liberally. Link notes to their category page. Link related notes to each other.
- **Category pages** are index pages that list all content in that topic. Format: "# Category Name" followed by bullet list of [[linked pages]].
- **Be hierarchical.** Broad categories (e.g., "Technology") can link to subcategories (e.g., "[[Machine Learning]]", "[[Web Development]]").
- **Create a _index page** if one doesn't exist. It should link to all category pages.
- **Merge duplicates** aggressively. Two notes about the same topic should become one.
- **Delete noise.** If content has no lasting value, don't create a note for it.
- **Keep content concise.** Summaries, not raw transcripts.

Respond ONLY with valid JSON."""

    client = _get_anthropic()
    response = await client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


# --- Outcome scoring ---


async def _score_outcomes(agent_id: UUID, notebook_id: UUID, config: dict, episodes: list[dict]) -> None:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, session_id, injected_items FROM injection_sessions "
        "WHERE persona_id = $1 AND completed_at IS NOT NULL AND scored_at IS NULL",
        agent_id,
    )

    for row in rows:
        session_id = row["session_id"]
        injected_items = row["injected_items"]
        if not injected_items:
            await pool.execute("UPDATE injection_sessions SET scored_at = now() WHERE id = $1", row["id"])
            continue

        # Build card previews
        cards: list[dict] = []
        for item in injected_items:
            key = item.get("key", "")
            if not key.startswith("page:"):
                continue
            page_id = UUID(key.split(":", 1)[1])
            page = await notebook_service.get_page(page_id, notebook_id)
            if page:
                cards.append({
                    "page_id": str(page_id),
                    "name": page["name"],
                    "preview": page["content_markdown"][:200],
                })

        if not cards:
            await pool.execute("UPDATE injection_sessions SET scored_at = now() WHERE id = $1", row["id"])
            continue

        # Build session summary
        session_eps = [ep for ep in episodes if ep.get("session_id") == session_id]
        if not session_eps:
            # Try fetching from DB
            session_eps_raw, _ = await memory_service.query_events(
                row["injected_items"][0].get("store_id") if injected_items else None,
                session_id=session_id, limit=100,
            ) if False else ([], False)
            # Skip if no episodes available
            await pool.execute("UPDATE injection_sessions SET scored_at = now() WHERE id = $1", row["id"])
            continue

        session_summary = _format_episodes_for_llm(session_eps)

        try:
            verdicts = await _score_outcomes_llm(config["monologue_model"], session_summary, cards)
            for v in verdicts:
                page_id_str = v.get("page_id", "")
                verdict = v.get("verdict", "")
                if page_id_str and verdict in ("success", "partial", "irrelevant", "override", "failure"):
                    # Update outcomes in notebook page metadata
                    await pool.execute(
                        "UPDATE notebook_pages SET metadata = metadata || "
                        "jsonb_build_object('outcomes', "
                        "  COALESCE(metadata->'outcomes', '{}'::jsonb) || "
                        "  jsonb_build_object($3, COALESCE((metadata->'outcomes'->>$3)::int, 0) + 1)"
                        ") WHERE id = $2 AND notebook_id = $1",
                        notebook_id, UUID(page_id_str), verdict,
                    )
        except Exception:
            logger.warning("Outcome scoring LLM call failed for session %s", session_id, exc_info=True)

        await pool.execute("UPDATE injection_sessions SET scored_at = now() WHERE id = $1", row["id"])


# --- Monologue generation ---


async def _generate_monologues(agent_id: UUID, history_id: UUID, config: dict, episodes: list[dict], watermark: dict) -> datetime | None:
    batch_size = config["monologue_batch_size"]
    last_mono_ts = watermark.get("last_monologue_event_at")

    # Get episodes not yet summarized into monologues
    if last_mono_ts:
        unsummarized = [ep for ep in episodes if ep["created_at"] > last_mono_ts]
    else:
        unsummarized = episodes

    if len(unsummarized) < batch_size:
        return None

    max_mono_ts = None
    for i in range(0, len(unsummarized), batch_size):
        batch = unsummarized[i : i + batch_size]
        if len(batch) < batch_size // 2:
            break
        try:
            text = await _generate_monologue_text(config["monologue_model"], batch)
            if text:
                start_ts = batch[0]["created_at"].isoformat() if batch[0].get("created_at") else ""
                end_ts = batch[-1]["created_at"].isoformat() if batch[-1].get("created_at") else ""
                await memory_service.push_event(
                    store_id=history_id,
                    agent_name="sleep_agent",
                    event_type="monologue",
                    content=text,
                    session_id=batch[0].get("session_id"),
                    metadata={"episode_range": {"start": start_ts, "end": end_ts}},
                )
                max_mono_ts = batch[-1]["created_at"]
        except Exception:
            logger.warning("Monologue generation failed", exc_info=True)
            break

    return max_mono_ts


# --- Execute curation actions ---


async def _execute_actions(agent_id: UUID, notebook_id: UUID, config: dict, result: dict) -> None:
    max_cards = config["max_pattern_cards"]
    pool = get_pool()

    # Count existing pattern cards
    card_count_row = await pool.fetchval(
        "SELECT COUNT(*) FROM notebook_pages WHERE notebook_id = $1 AND metadata->>'note_type' = 'pattern'",
        notebook_id,
    )
    card_count = card_count_row or 0

    # Build folder cache (category name -> folder_id)
    folder_cache: dict[str, UUID] = {}
    existing_folders = await pool.fetch(
        "SELECT id, name FROM notebook_folders WHERE notebook_id = $1", notebook_id,
    )
    for f in existing_folders:
        folder_cache[f["name"]] = f["id"]

    async def _ensure_folder(folder_name: str) -> UUID | None:
        if not folder_name:
            return None
        if folder_name in folder_cache:
            return folder_cache[folder_name]
        try:
            folder = await notebook_service.create_folder(notebook_id, folder_name, agent_id)
            folder_cache[folder_name] = folder["id"]
            return folder["id"]
        except Exception:
            return None  # Folder may already exist from race condition

    # Create notes
    for note_data in result.get("create_notes", []):
        note_type = note_data.get("type", "note")
        if note_type == "pattern" and card_count >= max_cards:
            continue

        metadata: dict = {
            "note_type": note_type,
            "keywords": note_data.get("keywords", []),
            "importance": note_data.get("importance", 0.5),
            "auto_inject": note_type == "category",  # Category pages are always available
            "source": "sleep_agent",
            "category": note_data.get("category", ""),
        }
        if note_type == "pattern":
            metadata["outcomes"] = {"success": 0, "partial": 0, "irrelevant": 0, "override": 0, "failure": 0}
            metadata["situation"] = note_data.get("situation", "")
            metadata["lessons"] = note_data.get("lessons", [])
            metadata["confidence"] = note_data.get("confidence", 0.5)
            card_count += 1

        # Create folder for the category if specified
        folder_id = await _ensure_folder(note_data.get("folder", ""))

        await notebook_service.create_page(
            notebook_id=notebook_id,
            name=note_data.get("title", "Untitled"),
            created_by=agent_id,
            folder_id=folder_id,
            content=note_data.get("content", ""),
            metadata=metadata,
        )

    # Update category pages (add new wiki links)
    for cat_update in result.get("update_categories", []):
        page_id_str = cat_update.get("page_id", "")
        if not page_id_str:
            continue
        page = await notebook_service.get_page(UUID(page_id_str), notebook_id)
        if not page:
            continue
        new_links = cat_update.get("add_links", [])
        if new_links:
            additions = "\n".join(f"- [[{link}]]" for link in new_links)
            new_content = page["content_markdown"] + f"\n{additions}"
            await notebook_service.update_page(
                page_id=UUID(page_id_str),
                notebook_id=notebook_id,
                updated_by=agent_id,
                content=new_content,
            )

    # Update notes
    for update in result.get("update_notes", []):
        page_id_str = update.get("page_id", "")
        if not page_id_str:
            continue
        page_id = UUID(page_id_str)
        page = await notebook_service.get_page(page_id, notebook_id)
        if not page:
            continue

        new_content = page["content_markdown"]
        additions = update.get("content_additions")
        if additions:
            new_content += f"\n\n{additions}"

        new_meta = dict(page.get("metadata", {}))
        if "keywords" in update:
            new_meta["keywords"] = update["keywords"]
        if update.get("importance") is not None:
            new_meta["importance"] = update["importance"]

        await notebook_service.update_page(
            page_id=page_id,
            notebook_id=notebook_id,
            updated_by=agent_id,
            content=new_content,
            metadata=new_meta,
        )

    # Merge notes
    for merge in result.get("merge_notes", []):
        source_ids = merge.get("source_page_ids", [])
        new_title = merge.get("new_title", "Merged Note")
        if len(source_ids) < 2:
            continue

        combined_content = []
        combined_keywords: set[str] = set()
        for pid_str in source_ids:
            page = await notebook_service.get_page(UUID(pid_str), notebook_id)
            if page:
                combined_content.append(page["content_markdown"])
                meta = page.get("metadata", {})
                combined_keywords.update(meta.get("keywords", []))

        if combined_content:
            await notebook_service.create_page(
                notebook_id=notebook_id,
                name=new_title,
                created_by=agent_id,
                content="\n\n---\n\n".join(combined_content),
                metadata={
                    "note_type": "note",
                    "keywords": list(combined_keywords),
                    "importance": 0.5,
                    "auto_inject": False,
                    "source": "sleep_agent",
                },
            )
            for pid_str in source_ids:
                await notebook_service.delete_page(UUID(pid_str), notebook_id)

    # Delete notes
    for page_id_str in result.get("delete_notes", []):
        await notebook_service.delete_page(UUID(page_id_str), notebook_id)


# --- Scheduler helpers ---


async def get_due_agents() -> list[UUID]:
    """Get agent IDs that are due for curation."""
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT u.id FROM users u "
        "LEFT JOIN sleep_configs sc ON sc.persona_id = u.id "
        "LEFT JOIN sleep_watermarks sw ON sw.persona_id = u.id "
        "WHERE u.type = 'persona' AND u.history_id IS NOT NULL AND u.notebook_id IS NOT NULL "
        "AND COALESCE(sc.enabled, true) = true "
        "AND (sw.last_run_at IS NULL OR "
        "     sw.last_run_at + (COALESCE(sc.interval_minutes, 60) * INTERVAL '1 minute') < now())"
    )
    return [row["id"] for row in rows]


# --- Main curation entry point ---


async def curate(agent_id: UUID) -> dict:
    """Full curation cycle for one agent. Called by scheduler or manual trigger."""
    config = await _load_sleep_config(agent_id)
    if not config["enabled"]:
        return {"status": "disabled"}

    resources = await _get_persona_resources(agent_id)
    notebook_id = resources["notebook_id"]
    history_id = resources["history_id"]

    watermark = await _get_watermark(agent_id)
    sources = config.get("curation_sources", ["history"])
    ws_ids = config.get("workspace_ids", [])

    # --- Gather data from configured sources ---

    # Personal history (always gathered for health detection + outcome scoring)
    episodes = await _get_episodes_since(history_id, watermark["last_event_at"])

    # Workspace history events
    ws_episodes = []
    if "history" in sources and ws_ids:
        ws_episodes = await _get_workspace_history_since(ws_ids, watermark["last_event_at"])

    # Notebook changes
    notebook_changes = []
    if "notebooks" in sources and ws_ids:
        notebook_changes = await _get_notebook_changes_since(ws_ids, watermark["last_event_at"])

    # New documents
    new_documents = []
    if "documents" in sources and ws_ids:
        new_documents = await _get_new_documents(ws_ids, watermark["last_event_at"])

    # Table changes
    table_changes = []
    if "tables" in sources and ws_ids:
        table_changes = await _get_table_changes_since(ws_ids, watermark["last_event_at"])

    # Check if there's anything to curate
    has_data = (
        episodes or ws_episodes or notebook_changes or new_documents or table_changes
    )
    if not has_data:
        return {"status": "no_new_data"}

    # Score outcomes for completed sessions (uses personal episodes)
    if episodes:
        await _score_outcomes(agent_id, notebook_id, config, episodes)

    # Health detection (personal episodes only)
    health = _detect_health_issues(episodes) if episodes else {}

    # Generate monologues from personal episodes
    max_mono_ts = None
    if episodes:
        max_mono_ts = await _generate_monologues(agent_id, history_id, config, episodes, watermark)

    # Gather existing notes for LLM context
    pool = get_pool()
    all_pages = await pool.fetch(
        "SELECT id, name, content_markdown, metadata FROM notebook_pages "
        "WHERE notebook_id = $1 AND metadata->>'note_type' IS NOT NULL "
        "AND metadata->>'note_type' != 'monologue'",
        notebook_id,
    )
    notes_summary = _format_notes_for_llm([dict(p) for p in all_pages])

    # Gather recent monologues
    monologue_rows = await pool.fetch(
        "SELECT content FROM history_events WHERE store_id = $1 AND event_type = 'monologue' "
        "ORDER BY created_at DESC LIMIT 10",
        history_id,
    )
    monologue_text = "\n".join(r["content"] for r in monologue_rows) if monologue_rows else "(no monologues)"

    # Build combined summary from all sources
    summary_parts = []

    if episodes:
        episodes_summary = _format_episodes_for_llm(episodes)
        summary_parts.append(f"## Personal Episodes\n{episodes_summary}")

    if ws_episodes:
        ws_summary = _format_episodes_for_llm(ws_episodes)
        summary_parts.append(f"## Workspace History\n{ws_summary}")

    if notebook_changes:
        nb_summary = _format_notebook_changes_for_llm(notebook_changes)
        summary_parts.append(f"## Notebook Changes\n{nb_summary}")

    if new_documents:
        doc_summary = _format_documents_for_llm(new_documents)
        summary_parts.append(f"## New Documents\n{doc_summary}")

    if table_changes:
        tbl_summary = _format_table_changes_for_llm(table_changes)
        summary_parts.append(f"## Table Changes\n{tbl_summary}")

    summary_parts.append(f"## Monologues\n{monologue_text}")
    full_summary = "\n\n".join(summary_parts)

    since_last = "unknown"
    all_timestamps = [
        ep.get("created_at") for ep in episodes
        if isinstance(ep.get("created_at"), datetime)
    ]
    if all_timestamps:
        since_last = str(datetime.now(timezone.utc) - min(all_timestamps))

    # LLM curation
    try:
        result = await _llm_curate(config["curation_model"], full_summary, notes_summary, since_last)
    except Exception as e:
        logger.warning("LLM curation failed: %s", e, exc_info=True)
        if episodes:
            last_ts = episodes[-1]["created_at"]
            await _set_watermark(agent_id, last_ts, max_mono_ts)
        return {"status": "curation_failed", "error": str(e),
                "episodes_processed": len(episodes), **health}

    # Merge heuristic health with LLM health
    llm_health = result.get("health", {})
    health = {**health, **llm_health}

    # Execute actions
    await _execute_actions(agent_id, notebook_id, config, result)

    # Update watermark
    if episodes:
        last_ts = episodes[-1]["created_at"]
        await _set_watermark(agent_id, last_ts, max_mono_ts)

    actions_summary = {
        "created": len(result.get("create_notes", [])),
        "updated": len(result.get("update_notes", [])),
        "merged": len(result.get("merge_notes", [])),
        "deleted": len(result.get("delete_notes", [])),
    }

    total_items = (
        len(episodes) + len(ws_episodes) + len(notebook_changes)
        + len(new_documents) + len(table_changes)
    )

    return {
        "status": "completed",
        "episodes_processed": len(episodes),
        "total_items_curated": total_items,
        "sources_used": [s for s in sources if s != "history" or episodes or ws_episodes],
        "actions": actions_summary,
        **health,
    }
