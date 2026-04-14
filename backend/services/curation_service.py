"""Curation service: user-invoked knowledge base curation.

Reads history events and other workspace data, uses an LLM to organize
them into wiki pages with categories and [[wiki links]].

This replaces the old sleep_service.py — no scheduling, no watermarks,
no persona dependency. The user triggers curation explicitly via MCP tool.
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


# --- Data gathering ---


async def _get_workspace_history(
    workspace_ids: list[UUID],
    after: datetime | None = None,
    agent_name_filter: list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """Get history events from workspace stores."""
    pool = get_pool()
    if not workspace_ids:
        return []

    agent_clause = ""
    args: list = [workspace_ids]
    if agent_name_filter:
        agent_clause = " AND he.agent_name = ANY($%d)" % (len(args) + 1)
        args.append(agent_name_filter)

    if after:
        args.append(after)
        ts_idx = len(args)
        args.append(limit)
        lim_idx = len(args)
        rows = await pool.fetch(
            "SELECT he.id, he.agent_name, he.event_type, he.content, he.created_at, "
            "h.name AS store_name "
            "FROM history_events he JOIN histories h ON h.id = he.store_id "
            f"WHERE h.workspace_id = ANY($1){agent_clause} AND he.created_at > ${ts_idx} "
            f"ORDER BY he.created_at ASC LIMIT ${lim_idx}",
            *args,
        )
    else:
        args.append(limit)
        lim_idx = len(args)
        rows = await pool.fetch(
            "SELECT he.id, he.agent_name, he.event_type, he.content, he.created_at, "
            "h.name AS store_name "
            "FROM history_events he JOIN histories h ON h.id = he.store_id "
            f"WHERE h.workspace_id = ANY($1){agent_clause} "
            f"ORDER BY he.created_at DESC LIMIT ${lim_idx}",
            *args,
        )
    return [dict(r) for r in rows]


async def _get_notebook_changes(
    workspace_ids: list[UUID], after: datetime | None = None, limit: int = 100,
) -> list[dict]:
    pool = get_pool()
    if not workspace_ids:
        return []
    if after:
        rows = await pool.fetch(
            "SELECT np.id, np.name, np.content_markdown, np.updated_at, n.name AS notebook_name "
            "FROM notebook_pages np JOIN notebooks n ON n.id = np.notebook_id "
            "WHERE n.workspace_id = ANY($1) AND np.updated_at > $2 "
            "ORDER BY np.updated_at ASC LIMIT $3",
            workspace_ids, after, limit,
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


async def _get_table_changes(
    workspace_ids: list[UUID], after: datetime | None = None, limit: int = 100,
) -> list[dict]:
    pool = get_pool()
    if not workspace_ids:
        return []
    if after:
        rows = await pool.fetch(
            "SELECT tr.id, tr.data, tr.updated_at, t.name AS table_name "
            "FROM table_rows tr JOIN tables t ON t.id = tr.table_id "
            "WHERE t.workspace_id = ANY($1) AND tr.updated_at > $2 "
            "ORDER BY tr.updated_at ASC LIMIT $3",
            workspace_ids, after, limit,
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


def _format_notebook_changes_for_llm(changes: list[dict]) -> str:
    if not changes:
        return "(no notebook changes)"
    lines = []
    for c in changes[:50]:
        content_preview = (c.get("content_markdown") or "")[:200]
        lines.append(f"[{c.get('notebook_name', '?')}/{c['name']}] {content_preview}")
    return "\n".join(lines)


def _format_table_changes_for_llm(changes: list[dict]) -> str:
    if not changes:
        return "(no table changes)"
    lines = []
    for c in changes[:50]:
        data_preview = str(c.get("data", {}))[:200]
        lines.append(f"[{c.get('table_name', '?')}] {data_preview}")
    return "\n".join(lines)


def _format_notes_for_llm(pages: list[dict]) -> str:
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


# --- LLM curation ---


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
     "category": str,             # Category name this belongs to
     "folder": str                # Folder name to file this under
   }}]
   - type "category": Create a category index page listing all known pages in that category using [[wiki links]].
   - type "note": A knowledge page about a specific topic. Link to its category page.
   - type "pattern": A recurring pattern. Include "situation", "lessons" (list), "confidence" (0-1).

2. "update_notes": [{{
     "page_id": str,
     "content_additions": str,
     "keywords": [str],
     "importance": float
   }}]

3. "merge_notes": [{{"source_page_ids": [str], "new_title": str, "category": str}}]

4. "delete_notes": [page_id strings]

5. "update_categories": [{{
     "page_id": str,
     "add_links": [str]
   }}]

## Guidelines
- **Categorize everything.** Every note should belong to a category.
- **Use [[wiki links]]** liberally. Link notes to their category page and related notes.
- **Category pages** list all content in that topic.
- **Merge duplicates** aggressively.
- **Delete noise.** If content has no lasting value, don't keep it.
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


# --- Execute curation actions ---


async def _execute_actions(notebook_id: UUID, user_id: UUID, result: dict) -> None:
    pool = get_pool()

    # Build folder cache
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
            folder = await notebook_service.create_folder(notebook_id, folder_name, user_id)
            folder_cache[folder_name] = folder["id"]
            return folder["id"]
        except Exception:
            return None

    # Create notes
    for note_data in result.get("create_notes", []):
        note_type = note_data.get("type", "note")
        metadata: dict = {
            "note_type": note_type,
            "keywords": note_data.get("keywords", []),
            "importance": note_data.get("importance", 0.5),
            "source": "curation",
            "category": note_data.get("category", ""),
        }
        if note_type == "pattern":
            metadata["situation"] = note_data.get("situation", "")
            metadata["lessons"] = note_data.get("lessons", [])
            metadata["confidence"] = note_data.get("confidence", 0.5)

        folder_id = await _ensure_folder(note_data.get("folder", ""))
        await notebook_service.create_page(
            notebook_id=notebook_id,
            name=note_data.get("title", "Untitled"),
            created_by=user_id,
            folder_id=folder_id,
            content=note_data.get("content", ""),
            metadata=metadata,
        )

    # Update category pages
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
                updated_by=user_id,
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
            updated_by=user_id,
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
                created_by=user_id,
                content="\n\n---\n\n".join(combined_content),
                metadata={
                    "note_type": "note",
                    "keywords": list(combined_keywords),
                    "importance": 0.5,
                    "source": "curation",
                },
            )
            for pid_str in source_ids:
                await notebook_service.delete_page(UUID(pid_str), notebook_id)

    # Delete notes
    for page_id_str in result.get("delete_notes", []):
        await notebook_service.delete_page(UUID(page_id_str), notebook_id)


# --- Main entry point ---


async def curate(
    *,
    workspace_id: UUID,
    notebook_id: UUID,
    user_id: UUID,
    source_store_ids: list[UUID] | None = None,
    agent_name_filter: list[str] | None = None,
    after: datetime | None = None,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """Run a curation cycle: gather data, ask LLM to organize, write wiki pages.

    Called by the MCP `curate` tool. The user triggers this explicitly.
    """
    workspace_ids = [workspace_id]

    # Gather data
    history_events = await _get_workspace_history(
        workspace_ids, after=after, agent_name_filter=agent_name_filter,
    )
    notebook_changes = await _get_notebook_changes(workspace_ids, after=after)
    table_changes = await _get_table_changes(workspace_ids, after=after)

    has_data = history_events or notebook_changes or table_changes
    if not has_data:
        return {"status": "no_new_data"}

    # Build summary
    summary_parts = []
    if history_events:
        summary_parts.append(f"## History Events\n{_format_episodes_for_llm(history_events)}")
    if notebook_changes:
        summary_parts.append(f"## Notebook Changes\n{_format_notebook_changes_for_llm(notebook_changes)}")
    if table_changes:
        summary_parts.append(f"## Table Changes\n{_format_table_changes_for_llm(table_changes)}")
    full_summary = "\n\n".join(summary_parts)

    # Get existing notes
    pool = get_pool()
    all_pages = await pool.fetch(
        "SELECT id, name, content_markdown, metadata FROM notebook_pages "
        "WHERE notebook_id = $1",
        notebook_id,
    )
    notes_summary = _format_notes_for_llm([dict(p) for p in all_pages])

    since_last = "unknown"
    all_timestamps = [
        ep.get("created_at") for ep in history_events
        if isinstance(ep.get("created_at"), datetime)
    ]
    if all_timestamps:
        since_last = str(datetime.now(timezone.utc) - min(all_timestamps))

    # LLM curation
    try:
        result = await _llm_curate(model, full_summary, notes_summary, since_last)
    except Exception as e:
        logger.warning("LLM curation failed: %s", e, exc_info=True)
        return {"status": "curation_failed", "error": str(e)}

    # Execute actions
    await _execute_actions(notebook_id, user_id, result)

    actions_summary = {
        "created": len(result.get("create_notes", [])),
        "updated": len(result.get("update_notes", [])),
        "merged": len(result.get("merge_notes", [])),
        "deleted": len(result.get("delete_notes", [])),
    }

    return {
        "status": "completed",
        "total_items_curated": len(history_events) + len(notebook_changes) + len(table_changes),
        "actions": actions_summary,
    }
