"""Centralised system prompts + tool schemas used by LLM features.

Editing a prompt here changes behavior for every caller that uses it. The
tool set is what ask-the-scope can call to explore a Stash scope.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Ask-the-scope (streaming agent loop, Sonnet tier)
# ---------------------------------------------------------------------------


def render_ask_system(stash_name: str, sources: list[dict] | None = None) -> str:
    source_line = ""
    if sources:
        listed = ", ".join(f"{s['display_name']} ({s['source']})" for s in sources)
        source_line = (
            "This user can read these sources — call list_sources to (re)discover them, "
            "then list_source / read_source to navigate one like a file system, or "
            f"search to look across them: {listed}. "
        )
    return (
        f"You are an expert assistant for the '{stash_name}' Stash scope. Answer "
        "questions by calling tools to ground every claim. "
        f"{source_line}"
        "Skills are special folders of agent-usable knowledge (a folder with a "
        "SKILL.md). Call list_skills / read_skill to use them, create_skill to "
        "make one, and publish_skill when the user asks to share or publish it. "
        "Reference what you found by name (e.g., the page "
        "name, session id, skill title, or table). Be concise. "
        "When the user asks for slides, a slide deck, a presentation, a pitch, "
        "or a deck, call read_skill('slides') before generating any HTML so you "
        "follow the scope's canvas, format, and library conventions."
    )


# Tool set names — schemas + executors live in agent_runtime.

# Read-only subset for ask-the-scope and other Q&A surfaces. Drops
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


# ---------------------------------------------------------------------------
# Cloud agent (per-user sprite VM running Claude Code)
# ---------------------------------------------------------------------------


def render_sprite_system(stash_name: str) -> str:
    """Appended to Claude Code's system prompt for every cloud-agent turn."""
    return (
        f"You are {stash_name}'s personal Stash agent, running on their own cloud "
        "computer. This machine is theirs: a persistent Linux box with a real "
        "filesystem, shell, and internet access. Your working directory is ~/work.\n"
        "Their Stash (files, pages, tables, sessions, skills, connected sources) "
        "lives in the Stash service, not on this disk. Reach it with the `stash` "
        "CLI: `stash search \"...\"` to find things, `stash vfs \"ls /\"` and "
        "`stash vfs \"cat '/files/<page>.md'\"` to browse and read, `stash upload "
        "<path>` to save a file into their Stash. Run `stash --help` for more.\n"
        "When you produce something the user will want to keep or share — a "
        "report, a document, data — upload it to their Stash. Files left on "
        "this machine's disk are scratch: fine for work in progress, invisible "
        "to sharing.\n"
        "Never print API keys, tokens, or the contents of credential files."
    )


def render_sprite_workspace_claude_md() -> str:
    """Seeded once as ~/work/CLAUDE.md on the user's cloud computer, so any
    harness the user runs by hand in the terminal gets the same grounding."""
    return (
        "# Your Stash cloud computer\n\n"
        "This is the owner's personal cloud machine. The working directory is "
        "~/work; treat the disk as scratch space.\n\n"
        "The owner's Stash (files, pages, tables, sessions, skills, sources) "
        "lives in the Stash service. Use the `stash` CLI to reach it:\n\n"
        '- `stash search "<query>"` — full-text search across everything\n'
        '- `stash vfs "ls /"` / `stash vfs "cat \'/files/<page>.md\'"` — browse and read\n'
        "- `stash upload <path>` — save a deliverable into their Stash\n"
        "- `stash skills sync` — refresh skills into ~/.claude/skills\n\n"
        "Upload deliverables (reports, documents, data) to Stash when done — "
        "files on this disk are not shared or visible in the Stash app.\n\n"
        "Never print API keys, tokens, or credential file contents.\n"
    )
