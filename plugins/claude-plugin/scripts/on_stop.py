#!/usr/bin/env python3
"""Stop hook: stream assistant's last message + push session summary to Octopus history."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_stdin_data, get_client, get_config, is_configured, load_state, save_state


def count_transcript_stats(transcript_path: str) -> dict:
    """Read the transcript file and count tool uses / files changed."""
    stats = {"tool_count": 0, "files_changed": set(), "tools_used": set()}
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("type") == "tool_use":
                    stats["tool_count"] += 1
                    tool_name = entry.get("name", "")
                    stats["tools_used"].add(tool_name)
                    tool_input = entry.get("input", {})
                    if isinstance(tool_input, dict):
                        fp = tool_input.get("file_path", "")
                        if fp and tool_name in ("Edit", "Write"):
                            stats["files_changed"].add(fp)
    except Exception:
        pass
    stats["files_changed"] = list(stats["files_changed"])
    stats["tools_used"] = list(stats["tools_used"])
    return stats


def main():
    if not is_configured():
        return

    state = load_state()
    if not state.get("streaming_enabled", True):
        return

    cfg = get_config()
    if not cfg["workspace_id"]:
        return

    data = get_stdin_data()

    try:
        with get_client() as client:
            # --- Stream the assistant's last message ---
            last_message = data.get("last_assistant_message", "")
            if last_message:
                client.push_event(
                    workspace_id=cfg["workspace_id"],
                    agent_name=cfg["agent_name"],
                    event_type="assistant_message",
                    content=last_message[:4000],
                    session_id=state.get("session_id", ""),
                )

            # --- Push session summary ---
            transcript_path = data.get("transcript_path", "")
            stats = count_transcript_stats(transcript_path) if transcript_path else {}

            tool_count = stats.get("tool_count", 0)
            files_changed = stats.get("files_changed", [])
            tools_used = stats.get("tools_used", [])

            parts = ["Session ended."]
            if tool_count:
                parts.append(f"{tool_count} tool uses.")
            if files_changed:
                parts.append(f"{len(files_changed)} files changed.")
            content = " ".join(parts)

            metadata = {
                "cwd": data.get("cwd", ""),
                "tool_count": tool_count,
                "files_changed": files_changed,
                "tools_used": tools_used,
            }

            client.push_event(
                workspace_id=cfg["workspace_id"],
                agent_name=cfg["agent_name"],
                event_type="session_end",
                content=content,
                session_id=state.get("session_id", ""),
                metadata=metadata,
            )
    except Exception:
        pass

    # Clear session ID
    state["session_id"] = ""
    save_state(state)


if __name__ == "__main__":
    main()
