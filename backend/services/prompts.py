"""Centralised system prompts + tool schemas used by LLM features.

Editing a prompt here changes behavior for every caller that uses it. The
tool set is what ask-the-workspace can call to explore a Stash Workspace.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Ask-the-workspace (streaming agent loop, Sonnet tier)
# ---------------------------------------------------------------------------


def render_ask_system(
    stash_name: str,
    sources: list[dict] | None = None,
    can_render_ui: bool = False,
) -> str:
    source_line = ""
    if sources:
        listed = ", ".join(f"{s['display_name']} ({s['source']})" for s in sources)
        source_line = (
            "This user can read these sources — call list_sources to (re)discover them, "
            "then list_source / read_source to navigate one like a file system, or "
            f"search to look across them: {listed}. "
        )
    canvas_line = ""
    if can_render_ui:
        canvas_line = (
            "You can render a live generative UI canvas in a panel beside the chat: "
            "create_canvas to render one, read_canvas + update_canvas to refine it. "
            "When the user would be better served by SEEING something — a dashboard, "
            "table, comparison, chart, summary, or a small form/buttons to act on — "
            "render or update a canvas built from pre-built blocks (heading, text, "
            "stat/stats, card, table, list, chart, form, button, divider) and only "
            "drop to an html block for layouts those can't express. Keep one canvas "
            "per topic: update the existing canvas instead of creating duplicates, "
            "and still give a short text reply saying what you put on it. "
        )
    return (
        f"You are an expert assistant for the '{stash_name}' Stash Workspace. Answer "
        "questions by calling tools to ground every claim. "
        f"{source_line}"
        "Skills are special folders of agent-usable knowledge (a folder with a "
        "SKILL.md). Call list_skills / read_skill to use them, create_skill to "
        "make one, and publish_skill when the user asks to share or publish it. "
        f"{canvas_line}"
        "Reference what you found by name (e.g., the page "
        "name, session id, skill title, or table). Be concise. "
        "When the user asks for slides, a slide deck, a presentation, a pitch, "
        "or a deck, call read_skill('slides') before generating any HTML so you "
        "follow the workspace's canvas, format, and library conventions."
    )


# Tool set names — schemas + executors live in agent_runtime.

# Full tool set including mutators. Use for surfaces where the agent is
# allowed to create / update / delete skills on the user's behalf.
STASH_TOOL_SET = (
    "search_history",
    "read_page",
    "create_page",
    "update_page",
    "edit_page",
    "create_folder",
    "move_page",
    "rename_page",
    "delete_page",
    "create_table",
    "insert_row",
    "update_row",
    "add_column",
    "delete_row",
    "copy_page",
    "copy_folder",
    "batch_move",
    "batch_delete",
    "batch_restore",
    "grep_pages",
    "list_files",
    "read_file",
    "query_table",
    "list_skills",
    "read_skill",
    "create_skill",
    "publish_skill",
    "update_skill",
    "unpublish_skill",
    "list_sources",
    "list_source",
    "read_source",
    "search",
    "query_source",
    "fetch_history",
    "create_canvas",
    "update_canvas",
    "read_canvas",
    "list_canvases",
)

# Canvas tools render the in-app generative-UI panel beside the chat.
CANVAS_TOOLS = frozenset({"create_canvas", "update_canvas", "read_canvas", "list_canvases"})

# Slack agent (talk-to-Stash bot): can create + update artifacts, but NOT
# destroy them. Slack is an untrusted surface, so destructive tools are held
# back to limit what a prompt-injected message can do. Canvas tools are dropped
# too — Slack has nowhere to render the UI panel.
SLACK_DESTRUCTIVE_TOOLS = frozenset(
    {"unpublish_skill", "delete_page", "delete_row", "batch_delete", "batch_restore"}
)
SLACK_HIDDEN_TOOLS = SLACK_DESTRUCTIVE_TOOLS | CANVAS_TOOLS
SLACK_TOOL_SET = tuple(t for t in STASH_TOOL_SET if t not in SLACK_HIDDEN_TOOLS)

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
    "list_sources",
    "list_source",
    "read_source",
    "search",
    "query_source",
    "fetch_history",
)
