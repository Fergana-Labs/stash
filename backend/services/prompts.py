"""Centralised system prompts + tool schemas used by LLM features.

Editing a prompt here changes behavior for every caller that uses it. The
tool set is what ask-the-workspace can call to explore a Stash Workspace.
"""

from __future__ import annotations

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
