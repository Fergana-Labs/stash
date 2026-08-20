# Travel planner — External Multiplayer end to end

One planner serving several travel agencies. Each agency is an **tenant**: what
the planner knows about *their* travellers is theirs alone, what it learns
about *the world* helps every agency, and no agency ever learns the others
exist.

## Run it

Mint a key in the Stash console (Developer Platform → API Keys), then:

```bash
cp .env.local.example .env.local     # add both keys
npm install
npm run dev                          # http://localhost:3200
```

Press **Seed the demo scenario**: Wanderly discovers a Vietnam e-visa took 19
working days against a published 3, and notes privately that Dr Okafor will
not fly overnight. Globetrek asks about its own trip.

Then in the console: **Curator → Run now** (2–4 minutes), and read what it
wrote under **Shared Wiki**.

Back here, pick **Globetrek** and ask whether a Vietnam e-visa will clear in
three weeks. It warns them off, citing "a peer tenant" — and nothing in
Globetrek's view names Wanderly or its traveller.

## Where the Stash calls are

All of them are in `lib/stash.ts`:

- `read(tenant, script)` → `POST /api/v1/me/vfs` — run a script against that
  customer's view. `/memory` is the shared wiki, `/files` their notepad and
  files, `/sessions` their transcripts.
- `record(tenant, tenantName, session, events)` → `POST /api/v1/me/sessions/events/batch`
  — one event per turn, tagged with the customer's tenant id. First sight of an
  id creates the tenant.

`lib/agent.ts` is the whole loop: read, answer, record. Everything else —
`api/tenants`, `api/transcript`, the page — is presentation, and a real product
would not need it.

## Session ids

A session belongs to one customer, so namespace the ids your app sends:
`wanderly:conv-1`, not `conv-1`. The second customer to reuse an id is
refused with a 400 rather than being filed into the first customer's
transcript.

Use `:` rather than `/`. Session ids are path parameters on the transcript
endpoints, so an id containing a slash still records and still turns up in
`find` and `grep`, but `cat` on its transcript 404s.
