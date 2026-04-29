Write extremely easy to consume code. Optimize for readability: skimmable, no cleverness, early returns.

### Write simple code
We are a startup. Therefore, code simplicity is our most important concern. Please NEVER
 - Attempt to preserve backwards compatibility when making an edit.
 - Use fallbacks when to save the UX when a primary path doesn't work (we'd rather fail fast, and this helps us to maintain as few codepaths as possible)
 
Here are some common code patterns that we need you to avoid:
 - Excessive try/catch: only use try/catch when there's a reasonable expectation that the code within might fail during normal usage. Every try/catch that we add adds another codepath that we need to maintain (the catch) and balloons complexity. In general, we follow the concept of "parse, don't validate" from TDD whenever possible. That is, we validate inputs at module boundaries, and within a module, we don't randomly add try/catch everywhere.
 
 - Unhelpful comments that reiterate what the code does: The point of a comment is to explain information that is not obvious from reading the code. A good rule of thumb: if your comment is an action (eg: sets the diff viewer open state), it is probably a bad comment. If it is a description (eg: the diff viewer state must be synced to our ui interaction server) it is likely a good comment.

### Be self-sufficient
If you are about to ask the user to do something for you, think about whether you can do it yourself.

- **Never ask the user to check logs.** Check them yourself — via running the server with captured output, MCPs for hosted servers, or ngrok inspector (`localhost:4040`).
- **Never ask permission to kill/restart local processes.** If you need to restart uvicorn, ngrok, or any dev server to make progress, just do it.
- **Never speculate about env vars, API keys, or config.** If you need to know whether something is set, check it yourself (e.g. `env | grep`, read `.env`, etc.). Just do it. Do not guess or assume. Do not ask the user. Check it yourself.
- **Never ask the user to test UI**. Use the playwright MCP to verify any UI changes that you make for the user. Do not ask the user to check to see if your UI changes worked or not. Use the Playwright MCP, and do it yourself.

### . Past Conversation Context

Previous Claude coding sessions are stored as `.jsonl` files in your ~/.claude file. Read these to understand prior decisions, debugging sessions, and context that isn't in git history.

When you create or update a PR, share the GitHub link with the user at the end of your session.

<!-- stash-context -->
## Stash

This repo uses [Stash](https://joinstash.ai) for shared agent history.
Your coding agent has the `stash` CLI on its PATH. Run `stash --help` to see commands.

Common reads (all support `--json`):
- `stash history search "<query>"` — full-text search across transcripts
- `stash history query --limit 20` — latest events
- `stash history agents` — who's been active
- `stash notebooks list --all` — shared notebooks
