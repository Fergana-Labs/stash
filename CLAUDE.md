We are a startup. Write extremely easy to consume code, optimize for how easy the code is to read. make the code skimmable.  avoid cleverness. use early returns

### Be self-sufficient
If you are about to ask the user to do something for you, think about whether you can do it yourself.

- **Never ask the user to check logs.** Check them yourself — via running the server with captured output, MCPs for hosted servers, or ngrok inspector (`localhost:4040`).
- **Never ask permission to kill/restart local processes.** If you need to restart uvicorn, ngrok, or any dev server to make progress, just do it.
- **Never speculate about env vars, API keys, or config.** If you need to know whether something is set, check it yourself (e.g. `env | grep`, read `.env`, etc.). Just do it. Do not guess or assume. Do not ask the user. Check it yourself.
- **Never ask the user to test UI**. Use the playwright MCP to verify any UI changes that you make for the user. Do not ask the user to check to see if your UI changes worked or not. Use the Playwright MCP, and do it yourself.

### . Past Conversation Context

Previous Claude coding sessions are stored as `.jsonl` files in your ~/.claude file. Read these to understand prior decisions, debugging sessions, and context that isn't in git history.


