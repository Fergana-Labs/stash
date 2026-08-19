# External Multiplayer, end to end

A truck-parts support agent serving two repair shops, of the shape Stash's
external customers ship. Each shop is an **org**: their history is theirs
alone, but what the agent learns about a fault code helps every shop. Stash is
what makes both true at once.

Three files, no framework:

- `stash.py` — the whole integration. Two calls: write a turn with the
  customer's org id, read back with the same org id.
- `agent.py` — reads that customer's world, answers with Claude, records the
  turn.
- `demo.py` — the scenario below.

## Run it

In the console (Developer Platform → API Keys), mint a key. Then:

```bash
export STASH_API_KEY=...          # the key you just minted
export ANTHROPIC_API_KEY=...      # the agent's own model key
export STASH_BASE_URL=http://localhost:3456   # omit for production

python demo.py
```

Acme hits a fault it has never seen and finds the fix. Beta asks about
something unrelated. Watch **Orgs** in the console: both appear on their first
turn, with their sessions.

Then curate. In the console, **Curator → Run now** (or wait for the nightly
pass), and when it finishes:

```bash
python demo.py verify
```

Beta now hits the fault Acme already solved, and its agent already knows.
The last step greps Beta's whole view for "acme" and finds nothing: Beta got
the lesson without learning that Acme exists.

## What to look at in the console

- **Orgs** — each customer, their sessions, files, connected sources, notepad.
- **Curator** — when it next runs, the exact prompt it will send, and which
  orgs feed the shared wiki.
- **Shared Wiki** — what every customer's agent reads. No org named anywhere.

## Session ids

A session belongs to one customer. Namespace the ids your app sends —
`acme/conv-1`, not `conv-1` — or the second customer to use an id is refused
with a 400 rather than being filed into the first customer's transcript.
