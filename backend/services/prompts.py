"""Centralised system prompts + tool schemas used by LLM features.

Two call sites consume this module:
- ask_service        : render_ask_system, STASH_TOOL_SET
- session_summarizer : SESSION_SUMMARY_SYSTEM, render_session_summary_user

Editing a prompt here changes behavior for every caller that uses it. The
tool set is what ask-the-workspace can call to explore a Stash Workspace.
"""

from __future__ import annotations

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
        "where this session left off. Start with the concrete work, not a "
        "generic heading. Do not include a markdown title like 'Session Summary'.\n\n"
        f"SESSION {source_label.upper()}:\n{transcript}"
    )


# ---------------------------------------------------------------------------
# Ask-the-workspace (streaming agent loop, Sonnet tier)
# ---------------------------------------------------------------------------


def render_ask_system(stash_name: str) -> str:
    return (
        f"You are an expert assistant for the '{stash_name}' Stash Workspace. Answer "
        "questions by calling tools to ground every claim. Use Stashes when "
        "the user asks to collect, bundle, publish, or organize a shareable subset of "
        "workspace material. Reference what you found by name (e.g., the page "
        "name, session id, Stash title, or table). Be concise."
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
    "list_stashes",
    "create_stash",
    "update_stash",
    "delete_stash",
)
RECIPIENT_TOOL_SET = ("read_page", "grep_pages", "list_files", "read_file")
