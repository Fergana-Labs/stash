# Atlas — a travel agent, and External Multiplayer end to end

Atlas is an AI travel agent you chat with about your own trip. Every traveller
who uses it is a **tenant**: what Atlas knows about *you* is yours alone, what
it learns about *the world* helps everyone it books for, and no traveller ever
learns another exists.

## Run it

Mint a key in the Stash console (Developer Platform → API Keys), then:

```bash
cp .env.local.example .env.local     # add both keys
npm install
npm run dev                          # http://localhost:3200
```

You land in Sam Ellery's account. Ask about a trip, start new chats, reopen old
ones from the sidebar — the history is read back out of Stash, not held in the
tab. The account switcher at the bottom of the sidebar moves you to Priya
Raman, whose Atlas knows nothing about Sam.

## The scenario worth watching

`npm run seed` (with the app running) plays four turns: Sam asks whether a
Vietnam e-visa will clear in three weeks, comes back to say it actually took 19
working days, and mentions he will not fly overnight. Priya, separately, asks
about getting six people from Berlin to Lisbon.

Then in the console: **Curator → Run now** (2–4 minutes), and read what it wrote
under **Shared Wiki**.

Back here, switch to Priya and ask whether a Vietnam e-visa will clear in three
weeks. Atlas warns her off, citing what it has seen before — and nothing in
Priya's view names Sam or says a word about aisle seats and overnight flights.

## Resetting between demos

`/admin` is the demo's control panel — deliberately not linked from the chat UI,
which is a product. It shows what each traveller can currently see, and puts the
demo back to its opening position: every conversation deleted, then Sam's
Vietnam thread written back — he asks whether three weeks is enough, returns to
say the e-visa took 19 working days, and mentions he will not fly overnight.
Priya is left with nothing, so her first question about Vietnam is genuinely her
first.

Those replies are fixture text, not generated. Sam's first answer has to be the
naive one; a live agent would now read the lesson out of the shared wiki and
answer correctly, which is the before-state the demo needs to keep.

The shared wiki survives a reset. It is what the curator built out of Sam's
lesson and what makes Priya's answer land — rebuild it with **Curator → Run
now** in the Stash console.

## Where the Stash calls are

Atlas has one tool, `search_stash`, and the model decides when to use it. Each
call runs one read-only shell command against that traveller's own view of
Stash, and the app draws it in the thread as it happens — `ls /memory`,
`cat "/memory/Visa & Entry Processing Times.md"` — with the number of lines it
got back. What the agent knows and where it got it are both on screen.

`lib/stash.ts` holds every HTTP call:

- `runScript(tenant, script)` → `POST /api/v1/me/vfs` — the tool's body. A
  non-zero exit is a normal shell result (grep exits 1 on no matches), so it
  comes back in the result rather than as an error. `/memory` is the shared
  wiki, `/files` their notepad and files, `/sessions` their transcripts.
- `record(tenant, tenantName, session, events)` → `POST /api/v1/me/sessions/events/batch`
  — one event per turn, tagged with the traveller's tenant id. First sight of an
  id creates the tenant. Each event carries its own timestamp: a batch that
  leaves them off lands every turn on the same instant, and the transcript comes
  back with the answer above the question.
- `listConversations(tenant)` / `readConversation(tenant, session)` — the
  sidebar and the chat you reopen from it, both read through that traveller's
  own view, so the history can only ever hold their own chats.

`lib/agent.ts` is the loop: the model asks to read, we run the command against
that tenant's view, hand back what it printed, and go round again until it
answers. `tenant` is the only isolation Stash needs — the model never reaches
another traveller's view, whatever command it writes.

It uses `@anthropic-ai/sdk` — the Messages API client — and deliberately **not**
the Claude Agent SDK. That one runs the `claude` CLI as a subprocess behind an
MCP boundary; `backend/services/tool_loop.py` abandoned it for the reasons in
its docstring, and this is the same native tool-use loop in TypeScript.

## Session ids

A session belongs to one traveller, so namespace the ids your app sends:
`sam:a3f9c2b1`, not `a3f9c2b1`. The second traveller to reuse an id is refused
with a 400 rather than being filed into the first traveller's transcript.

Use `:` rather than `/`. Session ids are path parameters on the transcript
endpoints, so an id containing a slash still records and still turns up in
`find` and `grep`, but `cat` on its transcript 404s.

Stash names a session's directory after its title rather than its id, which is
why reopening a chat greps `/sessions` for the id in `metadata.json` and reads
the transcript from alongside it.
