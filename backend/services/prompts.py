"""Centralised system prompts + tool schemas used by LLM features.

Three call sites consume this module:
- ask_service        : render_ask_system, STASH_TOOL_SET
- handoff_writer     : HANDOFF_WRITER_SYSTEM, render_handoff_seed, STASH_TOOL_SET
- session_summarizer : SESSION_SUMMARY_SYSTEM, render_session_summary_user

Editing a prompt here changes behavior for every caller that uses it. The
tool set is the writer's primary asset — same toolset ask-the-stash can call
to explore a stash.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Session summary (one-shot, Haiku tier)
# ---------------------------------------------------------------------------

SESSION_SUMMARY_SYSTEM = (
    "You summarize coding agent sessions for a developer who's picking up "
    "where the session left off. Be concrete and concise. Reference specific "
    "files and decisions by name."
)


def render_session_summary_user(transcript: str, source_label: str = "transcript") -> str:
    return (
        f"Summarize this coding session {source_label}. Include:\n"
        "1. What the session accomplished (1-2 sentences)\n"
        "2. Key files modified or created\n"
        "3. Important decisions made\n"
        "4. Any unfinished work or known issues\n\n"
        "Keep the summary concise and useful for someone picking up "
        "where this session left off.\n\n"
        f"SESSION {source_label.upper()}:\n{transcript}"
    )


# ---------------------------------------------------------------------------
# Ask-the-stash (streaming agent loop, Sonnet tier)
# ---------------------------------------------------------------------------


def render_ask_system(stash_name: str) -> str:
    return (
        f"You are an expert assistant for the '{stash_name}' stash. Answer questions "
        "by calling tools to ground every claim. Reference what you found by name "
        "(e.g., the wiki page name or table). Be concise."
    )


# Tool set names — schemas + executors live in agent_runtime.
STASH_TOOL_SET = (
    "search_history",
    "read_page",
    "grep_pages",
    "list_files",
    "read_file",
    "query_table",
    "list_skills",
    "read_skill",
)
RECIPIENT_TOOL_SET = ("read_page", "grep_pages", "list_files", "read_file")


# ---------------------------------------------------------------------------
# Handoff writer (agent loop, Sonnet tier, reuses ask tools)
# ---------------------------------------------------------------------------

HANDOFF_WRITER_SYSTEM = (
    "You are the writer of a stash's orientation document — a markdown handoff that "
    "a new coding agent will read first when it lands on this stash. Your job is to "
    "explore the stash using the tools provided, then produce a complete, accurate, "
    "concise document.\n\n"
    "If the seed includes a Stash Description, treat it as authoritative human input — "
    "the stash owner wrote it to tell you what matters. Build your document around it.\n\n"
    "Use the tools liberally on early turns to ground your understanding: search "
    "history, read top pages, list files, query tables. Cite specific page names, "
    "session ids, file names. Do NOT speculate beyond what you find.\n\n"
    "When you have enough context, emit the FINAL document as plain markdown in your "
    "next assistant turn (no tool calls). The document MUST have exactly these four "
    "H2 sections in this order:\n\n"
    "## What's in this stash\n"
    "## What's going on\n"
    "## Index — start here\n"
    "## Operating principles\n\n"
    "Be specific and skimmable. Aim for ~400-800 words total. If the stash is brand "
    "new (no sessions, no pages, no files), say so explicitly under each section "
    "with a brief 'start populating it by ...' nudge — do not hallucinate content."
)


@dataclass(slots=True)
class HandoffSeed:
    workspace_name: str
    description: str | None  # human-written Stash Description
    sessions: list[dict]  # [{session_id, agent_name, last_at, summary}]
    pages: list[dict]  # [{page_id, name}]
    file_counts: dict[str, int]  # {content_type: count}
    recent_files: list[str]  # last 20 names
    activity: list[dict]  # last 30 events


def render_handoff_seed(seed: HandoffSeed) -> str:
    parts: list[str] = []
    parts.append(f"Stash name: {seed.workspace_name}")
    if seed.description:
        parts.append(
            "\n--- Stash Description (human-written; treat as authoritative) ---\n"
            + seed.description.strip()
            + "\n--- end description ---"
        )

    if seed.sessions:
        parts.append("\nRecent sessions (newest first):")
        for s in seed.sessions:
            summary = (s.get("summary") or "").strip().replace("\n", " ")
            if len(summary) > 600:
                summary = summary[:600] + "…"
            parts.append(
                f"- session={s.get('session_id')} agent={s.get('agent_name') or '?'} "
                f"last_at={s.get('last_at')}\n  summary: {summary or '(no summary)'}"
            )
    else:
        parts.append("\nRecent sessions: (none yet)")

    if seed.pages:
        parts.append("\nTop-level wiki pages (use read_page to fetch bodies):")
        for p in seed.pages:
            parts.append(f"- {p.get('name')} (page_id={p.get('page_id')})")
    else:
        parts.append("\nTop-level wiki pages: (none yet)")

    if seed.file_counts:
        parts.append("\nFile counts by type:")
        for ct, n in sorted(seed.file_counts.items(), key=lambda kv: -kv[1]):
            parts.append(f"- {ct or 'unknown'}: {n}")
    if seed.recent_files:
        parts.append("\nMost recent files:")
        for n in seed.recent_files:
            parts.append(f"- {n}")

    if seed.activity:
        parts.append("\nRecent activity (last 14 days):")
        for ev in seed.activity:
            parts.append(
                f"- {ev.get('ts')} kind={ev.get('kind')} "
                f"target={ev.get('target_label') or ev.get('target_id')}"
            )

    parts.append("\nNow explore via tools as needed, then emit the final handoff document.")
    return "\n".join(parts)
