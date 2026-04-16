"""Turn a normalized tool_use event into (content, metadata) for the history store.

Tool names are already normalized to lowercase canonical names by each plugin's
adapter (see event.py). This module doesn't need to know which agent called it.
"""

from __future__ import annotations

import json


def summarize_tool_use(
    tool_name: str,
    tool_input: dict,
    tool_response: dict | None,
) -> tuple[str, dict]:
    metadata: dict = {}

    if tool_name == "edit":
        file_path = tool_input.get("file_path", "unknown")
        metadata = {
            "file_path": file_path,
            "old_preview": tool_input.get("old_string", "")[:100],
            "new_preview": tool_input.get("new_string", "")[:100],
        }
        content = f"Edited {file_path}"

    elif tool_name == "write":
        file_path = tool_input.get("file_path", "unknown")
        metadata = {"file_path": file_path}
        content = f"Created/wrote {file_path}"

    elif tool_name == "bash":
        command = tool_input.get("command", "")[:300]
        metadata = {"command": command}
        content = f"Ran: {command}"
        if tool_response:
            stdout = str(tool_response.get("stdout", ""))[:500]
            stderr = str(tool_response.get("stderr", ""))[:200]
            exit_code = tool_response.get("exitCode", tool_response.get("exit_code"))
            if stdout:
                metadata["stdout_preview"] = stdout
            if stderr:
                metadata["stderr_preview"] = stderr
            if exit_code is not None:
                metadata["exit_code"] = exit_code

    elif tool_name == "agent":
        desc = tool_input.get("description", tool_input.get("prompt", ""))[:200]
        content = f"Launched agent: {desc}"
        metadata = {"subagent_type": tool_input.get("subagent_type", "")}

    elif tool_name == "read":
        file_path = tool_input.get("file_path", "unknown")
        content = f"Read {file_path}"
        metadata = {"file_path": file_path}

    elif tool_name == "glob":
        pattern = tool_input.get("pattern", "")
        content = f"Glob: {pattern}"
        metadata = {"pattern": pattern}

    elif tool_name == "grep":
        pattern = tool_input.get("pattern", "")
        content = f"Grep: {pattern}"
        metadata = {"pattern": pattern, "path": tool_input.get("path", "")}

    else:
        content = f"{tool_name}: {str(tool_input)[:200]}"
        metadata = {"tool_input_preview": str(tool_input)[:500]}

    # Include response preview for non-read-only tools
    if tool_response and tool_name not in ("read", "glob", "grep"):
        if isinstance(tool_response, dict):
            metadata["response_preview"] = json.dumps(tool_response)[:500]
        else:
            metadata["response_preview"] = str(tool_response)[:500]

    return content, metadata
