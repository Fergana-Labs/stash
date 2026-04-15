#!/usr/bin/env python3
"""PostToolUse hook (async): stream tool call + result to Octopus history."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_stdin_data, get_client, get_config, is_configured, load_state


def summarize_tool_use(tool_name: str, tool_input: dict, tool_response: dict | None) -> tuple[str, dict]:
    """Build a human-readable summary and metadata from a tool use."""
    metadata: dict = {}

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
        if tool_response:
            stdout = str(tool_response.get("stdout", ""))[:500]
            stderr = str(tool_response.get("stderr", ""))[:200]
            exit_code = tool_response.get("exitCode")
            if stdout:
                metadata["stdout_preview"] = stdout
            if stderr:
                metadata["stderr_preview"] = stderr
            if exit_code is not None:
                metadata["exit_code"] = exit_code

    elif tool_name == "Agent":
        desc = tool_input.get("description", tool_input.get("prompt", ""))[:200]
        content = f"Launched agent: {desc}"
        metadata = {"subagent_type": tool_input.get("subagent_type", "")}

    elif tool_name in ("Read", "Glob", "Grep"):
        # Stream read-only tools too, just with less detail
        if tool_name == "Read":
            content = f"Read {tool_input.get('file_path', 'unknown')}"
            metadata = {"file_path": tool_input.get("file_path", "")}
        elif tool_name == "Glob":
            content = f"Glob: {tool_input.get('pattern', '')}"
            metadata = {"pattern": tool_input.get("pattern", "")}
        elif tool_name == "Grep":
            content = f"Grep: {tool_input.get('pattern', '')}"
            metadata = {"pattern": tool_input.get("pattern", ""), "path": tool_input.get("path", "")}

    else:
        content = f"{tool_name}: {str(tool_input)[:200]}"
        metadata = {"tool_input_preview": str(tool_input)[:500]}

    # Include tool response summary for all tools
    if tool_response and tool_name not in ("Read", "Glob", "Grep"):
        resp_str = str(tool_response)[:500] if not isinstance(tool_response, dict) else json.dumps(tool_response)[:500]
        metadata["response_preview"] = resp_str

    return content, metadata


def main():
    if not is_configured():
        return

    state = load_state()
    if not state.get("streaming_enabled", True):
        return

    data = get_stdin_data()
    tool_name = data.get("tool_name", "")
    if not tool_name:
        return

    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}

    tool_response = data.get("tool_response")

    cfg = get_config()
    if not cfg["workspace_id"]:
        return

    content, metadata = summarize_tool_use(tool_name, tool_input, tool_response)
    metadata["cwd"] = data.get("cwd", "")

    try:
        with get_client() as client:
            client.push_event(
                workspace_id=cfg["workspace_id"],
                agent_name=cfg["agent_name"],
                event_type="tool_use",
                content=content,
                session_id=state.get("session_id", ""),
                tool_name=tool_name,
                metadata=metadata,
            )
    except Exception:
        pass


if __name__ == "__main__":
    main()
