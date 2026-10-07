"""Released instructions for native SessionStart context.

This deliberately does not install a SKILL.md. Generic skill synchronization
has no draft/release boundary, and a file on disk does not prove context use.
The backend records an offer here; transcript capture supplies load evidence.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from stashai.plugin.event import HookEvent
    from stashai.plugin.stash_client import StashClient

MAX_INSTRUCTION_CHARS = 16000
MAX_CONTEXT_CHARS = 64000
_SOURCE_FORMATS = {"codex_cli": "codex", "claude_code": "claude_code"}


def instruction_context(delivery: dict) -> str:
    """Render an exact, identifiable instruction snapshot; reject corruption."""
    delivery_id = str(UUID(str(delivery["id"])))
    change_id = str(UUID(str(delivery["change_id"])))
    text = delivery["content"]
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_INSTRUCTION_CHARS:
        raise ValueError("Invalid released instruction text")
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest != delivery["content_sha256"]:
        raise ValueError("Released instruction content hash does not match")
    return (
        f'<stash-workbench-instruction delivery="{delivery_id}" '
        f'version="{change_id}" sha256="{digest}">\n'
        f"{text}\n</stash-workbench-instruction>"
    )


def released_instruction_context(client: StashClient, cfg: dict, event: HookEvent) -> str:
    """Best-effort fetch for supported harnesses; failures never break a session.

    No local cache: a stale cache could silently restore a rolled-back version.
    No receipt is submitted here because printing hook output is not proof the
    harness accepted it into its model-visible context.
    """
    source_format = _SOURCE_FORMATS.get(cfg.get("client"))
    if not source_format or not event.session_id or not event.cwd:
        return ""
    try:
        result = client.workbench_instruction_delivery(event.session_id, source_format, event.cwd)
        contexts = [instruction_context(item) for item in result["deliveries"]]
        context = "\n\n".join(contexts)
        if len(context) > MAX_CONTEXT_CHARS:
            return ""
        return context
    except Exception:
        return ""
