# stash-sdk

Python client for [Stash](https://joinstash.ai) — shared memory for AI
agents. One dependency (httpx), fully typed.

```bash
pip install stash-sdk
```

```python
from stash_sdk import Stash

stash = Stash()  # reads STASH_API_KEY (and optional STASH_URL) from env

stash.push_event(
    agent_name="my-agent",
    event_type="user_message",
    content="Can you rebook my Lisbon trip?",
    session_id="sam:trip-114",
)
hits = stash.search_events("Lisbon")
```

Everything the API offers is a method on `Stash`: events and transcripts,
pages and folders, files, tables, and Skills. Errors raise `StashError`
with the API's status code and detail — nothing fails silently.

The full API reference lives at [joinstash.ai/docs](https://joinstash.ai/docs).
