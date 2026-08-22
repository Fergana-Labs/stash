"""A truck-parts support agent, of the shape Stash's external customers ship.

It serves many repair shops. Each shop is an org: their history is theirs
alone, but what the agent learns about a fault code should help every shop.
Stash is what makes both true at once.
"""

import httpx

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a truck-parts support agent for a repair-shop customer.
Answer in two sentences at most. Use the context when it is relevant, and say
which part number to fit when you know it. Never mention other customers by
name — you do not know who they are."""


def answer(stash, anthropic_key: str, org: str, org_name: str, session: str, question: str) -> str:
    # Read this customer's world before answering: the shared wiki everyone's
    # agent reads, plus this customer's own notepad.
    context = _context(stash, org)
    reply = _claude(anthropic_key, context, question)
    stash.record(org, org_name, session, [("user_message", question), ("assistant_message", reply)])
    return reply


def _context(stash, org: str) -> str:
    """Everything this customer is allowed to know: the shared wiki, and their
    own notepad. Read a root at a time — the VFS shell has no stderr
    redirection, so one path that matches nothing fails the whole command.
    Cat only *.md: wiki categories are subfolders, and cat on a directory
    fails the command too."""
    parts = []
    for root in ("/memory", "/files/notepad"):
        if stash.read(org, f"ls {root}").strip():
            parts.append(stash.read(org, f"cat {root}/*.md"))
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
            "max_tokens": 300,
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
    return "".join(block["text"] for block in resp.json()["content"] if block["type"] == "text")
