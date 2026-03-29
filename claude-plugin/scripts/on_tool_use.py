#!/usr/bin/env python3
"""PostToolUse hook (async): stream tool activity to Boozle history."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_stdin_data, get_client, get_config, is_configured, load_state

# Tools that are too noisy to stream by default
EXCLUDED_TOOLS = {"Read", "Glob", "Grep", "ToolSearch"}


def summarize_tool_use(tool_name: str, tool_input: dict) -> tuple[str, dict]:
    """Build a human-readable summary and metadata from a tool use."""
    metadata = {}

    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "unknown")
        old = tool_input.get("old_string", "")[:100]
        new = tool_input.get("new_string", "")[:100]
        content = f"Edited {file_path}"
        metadata = {"file_path": file_path, "old_preview": old, "new_preview": new}

    elif tool_name == "Write":
        file_path = tool_input.get("file_path", "unknown")
        content = f"Created/wrote {file_path}"
        metadata = {"file_path": file_path}

    elif tool_name == "Bash":
        command = tool_input.get("command", "")[:300]
        content = f"Ran: {command}"
        metadata = {"command": command}

    elif tool_name == "Agent":
        desc = tool_input.get("description", tool_input.get("prompt", ""))[:200]
        content = f"Launched agent: {desc}"
        metadata = {"subagent_type": tool_input.get("subagent_type", "")}

    else:
        content = f"{tool_name}: {str(tool_input)[:200]}"
        metadata = {"tool_input_preview": str(tool_input)[:500]}

    return content, metadata


def main():
    if not is_configured():
        return

    state = load_state()
    if not state.get("streaming_enabled", True):
        return

    data = get_stdin_data()
    tool_name = data.get("tool_name", "")

    if tool_name in EXCLUDED_TOOLS:
        return

    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}

    cfg = get_config()
    if not cfg["workspace_id"] or not cfg["history_store_id"]:
        return

    content, metadata = summarize_tool_use(tool_name, tool_input)
    metadata["cwd"] = data.get("cwd", "")

    try:
        with get_client() as client:
            client.push_event(
                workspace_id=cfg["workspace_id"],
                store_id=cfg["history_store_id"],
                agent_name=cfg["agent_name"],
                event_type="tool_use",
                content=content,
                session_id=state.get("session_id", ""),
                tool_name=tool_name,
                metadata=metadata,
            )
            # Cloud reachable — opportunistically flush any pending local events
            try:
                from config import OFFLINE_DB_PATH
                import offline_db
                offline_db.try_flush_pending(OFFLINE_DB_PATH, client, cfg)
            except Exception:
                pass
    except Exception:
        # Cloud unavailable — queue locally for later sync
        try:
            from config import OFFLINE_DB_PATH
            import offline_db
            offline_db.queue_event(
                db_path=OFFLINE_DB_PATH,
                store_id=cfg["history_store_id"],
                agent_name=cfg["agent_name"],
                event_type="tool_use",
                content=content,
                session_id=state.get("session_id", ""),
                tool_name=tool_name,
                metadata=metadata,
            )
        except Exception:
            pass  # truly fire-and-forget


if __name__ == "__main__":
    main()
