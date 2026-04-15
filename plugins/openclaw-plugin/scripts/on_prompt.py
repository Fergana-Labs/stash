#!/usr/bin/env python3
"""prompt.submit: stream user prompt + inject context.

Openclaw protocol: to add context to a prompt, print JSON to stdout with a
`contextInject` key (documented at openclaw.dev/docs/hooks#prompt-submit).
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
    print(json.dumps({"contextInject": context}))


if __name__ == "__main__":
    main()
