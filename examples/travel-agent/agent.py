"""A travel-planning agent serving several agencies.

Each agency is an **org**. What the agent knows about *their* travellers —
who hates red-eyes, which corporate card, the client who always extends by a
weekend — is theirs alone. What it learns about *the world* — that this
consulate takes three weeks, that this airline reroutes through Doha in
winter — should help every agency, without any of them learning who the
others are.

Stash is what makes both true at once. Two calls do it: record each turn with
the agency's org id, and read back with the same org id.
"""

import httpx

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a travel planner working for a travel agency.

Context you are given comes from two places: general travel knowledge learned
across many agencies, and this agency's own notes about their travellers. Use
both. Be concrete — name airlines, airports, visa timelines, neighbourhoods.
Three sentences at most unless asked for an itinerary.

You do not know which other agencies exist and must never speculate about
them."""


def answer(stash, anthropic_key: str, org: str, org_name: str, session: str, question: str) -> str:
    # Everything this agency's planner is allowed to know: the shared wiki at
    # /memory, and their own notepad and files under /files.
    context = _context(stash, org)
    reply = _claude(anthropic_key, context, question)
    stash.record(org, org_name, session, [("user_message", question), ("assistant_message", reply)])
    return reply


def _context(stash, org: str) -> str:
    """Everything this customer is allowed to know: the shared wiki, and their
    own notepad. Read a root at a time — the VFS shell has no stderr
    redirection, so one path that matches nothing fails the whole command."""
    parts = []
    for root in ("/memory", "/files/notepad"):
        if stash.read(org, f"ls {root}").strip():
            parts.append(stash.read(org, f"cat {root}/*"))
    return "\n\n".join(parts)


def _claude(api_key: str, context: str, question: str) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 400,
            "system": SYSTEM,
            "messages": [
                {
                    "role": "user",
                    "content": f"What we know:\n{context or '(nothing yet)'}\n\n{question}",
                }
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return "".join(b["text"] for b in resp.json()["content"] if b["type"] == "text")
