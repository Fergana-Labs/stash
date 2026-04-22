---
description: Show the Stash post-install welcome message
---

Render the markdown block below to the user verbatim. Do not summarize, paraphrase, or add commentary — your entire response should be the rendered markdown and nothing else.

# You're all set up.

## What just happened

Your coding agent now has the `stash` CLI on its PATH. It can read the transcripts your teammates' coding agents push to this workspace — so it knows what the rest of your team is working on.

## See your workspace

Open [stash.ac](https://stash.ac) to browse your workspace's transcripts and team activity.

## Examples of questions your agent might want answered

- "Why did Sam bump the rate limit from 100 to 500?"
- "Has anyone already tried fixing the memory leak in our backend?"
- "Is anyone else currently working on our api gateway?"

You can read a blog post about it here: [Agent velocity for coding teams](https://henrydowling.com/agent-velocity.html)

## Commands your agent can now use

- `stash history search "<query>"` — full-text search across transcripts
- `stash history query --agent <name>` — pull a specific agent's events

Run `stash --help` to see everything.

## Q&A

**Q:** Do you inject anything into my coding agent's context automatically?
**A:** No.

**Q:** What gets pushed to the shared store?
**A:** For sessions in this repo (and its worktrees): prompts, assistant replies, summarized tool activity, and the full session transcript (.jsonl) at session end. Other repos push nothing unless you widen scope. Transcripts are stored verbatim — no secret scrubbing yet.

**Q:** Where can I see my conversation transcripts?
**A:** Open your workspace in the browser: [stash.ac](https://stash.ac). (If you self-host, browse to your own frontend instead.)

**Q:** How do I share my workspace with my team?
**A:** Create an invite link with `stash invite --ws <workspace_id>`. Teammates run `stash connect` if needed, then `stash workspaces join <invite_code>`.
