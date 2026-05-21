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
        "name, session id, Stash title, or table). Be concise. "
        "When the user asks for slides, a slide deck, a presentation, a pitch, "
        "or a deck, call read_skill('slides') before generating any HTML so you "
        "follow the workspace's canvas, format, and library conventions."
    )


# Tool set names — schemas + executors live in agent_runtime.

# Full tool set including mutators. Use for surfaces where the agent is
# allowed to create / update / delete stashes on the user's behalf.
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

# Read-only subset for ask-the-workspace and other Q&A surfaces. Drops
# the write tools so a prompt-injected request can't trigger mutations
# even if the model decides to play along. Service-layer permission
# checks would still reject, but this is belt-and-suspenders.
ASK_TOOL_SET = (
    "search_history",
    "read_page",
    "grep_pages",
    "list_files",
    "read_file",
    "query_table",
    "list_skills",
    "read_skill",
    "list_stashes",
)
