# Sharing Demo — Script & Build Plan

## The Story

Henry investigates something in Claude Code. He shares his **finding** to Stash — not a raw transcript, but a packaged artifact: a curated summary on top, the full conversation and any generated files underneath. He gets a link. Sam pastes that link into his own Claude Code and asks questions about it.

---

## Demo Script

### Scene 1: The Investigation (Henry's terminal, ~60s)

Henry is in Claude Code, working in the Stash repo.

> **Henry:** "There's been a spike in 401s on the transcript upload endpoint. Can you investigate?"

Claude digs in — reads logs, checks the auth middleware, traces the token validation path, finds the root cause (a clock-skew issue in JWT expiry validation).

Claude produces a natural summary at the end:
> "The 401 spike is caused by a 30-second clock skew between the auth service and the API server. Tokens minted in the last 30s of their TTL are rejected because the API server's clock is ahead. The fix is to add a `leeway` parameter to the JWT decode call."

### Scene 2: The Share (Henry's terminal, ~15s)

> **Henry:** "Share that with Sam."

Claude runs:
```
stash share --title "Auth 401 spike — clock skew in JWT validation"
```

Output:
```
Sharing session a3f2c8d1…
  Attached error_log.csv
Shared!  https://app.joinstash.ai/v/auth-401-spike-clock-skew-a8f2k1
```

What happened behind the scenes:
1. Auto-detected the current Claude Code session ID
2. Extracted the artifact: first user prompt ("Question") + last assistant message ("Finding")
3. Converted the full conversation to readable markdown
4. Created a notebook with two pages: **Summary** and **Full Transcript**
5. Uploaded any generated files (CSVs, images, etc.)
6. Uploaded the raw JSONL transcript blob for future reference
7. Bundled everything into a public View and printed the URL

### Scene 3: The Web View (browser, ~10s)

Cut to the browser showing the View at `/v/auth-401-spike-clock-skew-a8f2k1`:
- Clean title and workspace attribution
- **Summary** page: the question and finding, rendered as proper markdown
- **Full Transcript** page: the complete conversation, expandable
- Attached files listed below
- Fork button to pull the artifact into your own workspace

### Scene 4: The Consumption (Sam's terminal, ~30s)

Sam is in his own Claude Code session.

> **Sam:** "Henry shared this with me: https://app.joinstash.ai/v/auth-401-spike-clock-skew-a8f2k1 — can you read it and tell me what he found? Is it something we should fix before the release?"

Claude fetches the URL with `?format=text`, gets clean markdown back, and responds conversationally — it knows the finding, the root cause, the proposed fix, and which files were touched. Sam can ask follow-up questions as if Claude had done the investigation itself.

---

## What We Built

### `stash share` CLI command (cli/main.py)

New top-level command:
```
stash share [--title "..."] [--session <id>] [--file path ...] [--ws <id>]
```

- **Auto-detects session ID** from `~/.claude/plugins/data/stash/state.json`
- **Extracts artifact** from the JSONL: first user prompt + last assistant message (the bookends of the conversation — the question and the answer)
- **Creates a notebook** with two pages:
  - "Summary" — the curated Question + Finding
  - "Full Transcript" — the complete conversation as markdown
- **Uploads attached files** via `--file` flag (repeatable)
- **Uploads the raw transcript** blob for full fidelity
- **Creates a public View** bundling notebook + files
- **Prints the shareable URL**

### Markdown rendering on `/v/[slug]` (frontend)

Notebook pages now render with `react-markdown` + `remark-gfm` instead of a `<pre>` tag. Uses the existing `.markdown-content` CSS class. The artifact looks like a real document, not raw markdown source.

### `?format=text` on the public view API (backend)

`GET /api/v1/views/{slug}?format=text` returns plain markdown text (Content-Type: `text/markdown`). This is how another agent consumes the artifact — WebFetch the URL, get clean content, no HTML parsing needed.

---

## How Each Piece Connects

```
Henry's Claude Code session
    │
    ├── hooks stream events to Stash (already existed)
    │
    └── `stash share` (NEW)
         │
         ├── reads JSONL from ~/.claude/projects/
         ├── extracts artifact (question + finding)
         ├── creates notebook (Summary + Full Transcript)
         ├��─ uploads files
         └── publishes public View
              │
              ├── Web: /v/{slug} renders with markdown (UPDATED)
              │
              └── API: /api/v1/views/{slug}?format=text (NEW)
                   │
                   └── Sam's Claude Code fetches this
```

## Demo Prep Checklist

- [ ] Install the updated CLI from this branch (`pip install -e .` or copy to main repo)
- [ ] Pick a good investigation to do live (or pre-record Scene 1)
- [ ] Verify the View renders correctly on the production frontend
- [ ] Test the `?format=text` consumption path from a second Claude Code session
- [ ] Have Sam's workspace ready (or use the same workspace)
