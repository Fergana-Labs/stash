#!/usr/bin/env python3
"""UserPromptSubmit: stream prompt + inject context.

Codex injection protocol: print JSON with `additional_context` on stdout
(per developers.openai.com/codex/hooks).
"""

import json

from config import DATA_DIR, ESCALATION_DIR, get_client, get_config, get_stdin_data, is_configured
from hooks import build_injection_context, stream_user_message
from state import load_state

from adapt import adapt_prompt


def _injection_disabled(cfg: dict) -> bool:
    return cfg.get("inject_context", "true").lower() in ("false", "0", "no", "off")


def main():
    if not is_configured():
        return
    event = adapt_prompt(get_stdin_data())
    cfg = get_config()
    state = load_state(DATA_DIR)

    with get_client() as client:
        stream_user_message(client, cfg, state, event.prompt_text)

    if _injection_disabled(cfg):
        return

    context = build_injection_context(cfg, state, DATA_DIR, ESCALATION_DIR)
    print(json.dumps({"additional_context": context}))


if __name__ == "__main__":
    main()
