---
description: Show the Stash post-install welcome message
---

Render the markdown block below to the user verbatim. Do not summarize, paraphrase, or add commentary — your entire response should be the rendered markdown and nothing else.

# You're all set up.

## What just happened

Your coding agent now has the `stash` CLI on its PATH. It can read transcripts, notebooks, tables, and files that your teammates' coding agents push to this workspace — so it knows what the rest of your team is working on.

## See your workspace

Open [app.joinstash.ai](https://app.joinstash.ai) to browse your workspace's transcripts and team activity.

## Commands your agent can now use

```
stash history search "<query>"          # full-text search across transcripts
stash history query --agent <name>      # pull a specific agent's events
stash notebooks list --all              # browse shared notebooks
stash tables list --ws <workspace_id>   # list workspace tables
stash files list --ws <workspace_id>    # list workspace files
```

Run `stash --help` to see everything.

## Q&A

**Q:** Do you inject anything into my coding agent's context automatically?
**A:** No.

**Q:** What gets pushed to the shared store?
**A:** For sessions in this repo (and its worktrees): prompts, assistant replies, summarized tool activity, and the full session transcript at session end. Other repos push nothing unless you widen scope.

**Q:** Where can I see my conversation transcripts?
**A:** Open your workspace in the browser: [app.joinstash.ai](https://app.joinstash.ai).

**Q:** How do I share my workspace with my team?
**A:** `stash invite create --ws <workspace_id>` generates a magic-link invite. Teammates click the link or run `stash connect` and paste the code.
