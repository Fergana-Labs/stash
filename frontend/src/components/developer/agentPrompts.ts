// The console's copy-paste prompts: written for the developer's coding agent,
// not for a human. Each carries everything the agent needs — endpoints,
// payload shapes, and the rules that are easy to get wrong — so pasting one
// into Claude Code / Cursor pointed at the developer's codebase is the whole
// integration step.
//
// Install is the one-stop shop: wire live traffic AND load whatever history
// already exists. Backfill alone is the advanced path, for a stash that is
// already wired and only missing its history.

export const INSTALL_PROMPT = `Wire Stash (https://api.joinstash.ai) into this app so our agent has
per-user memory: every user's agent reads a shared knowledge wiki plus
that user's own private memory, and what our users say feeds back in.
Then load our existing history, so memory starts full instead of empty.

Context:
- Our Stash API key is in $STASH_API_KEY. It can read the knowledge base
  and record sessions — never delete or rewrite.
- user_id is our own id for an end user, and it is the isolation
  boundary: a read scoped to one user can never see another user's
  material. First sight of a new user_id creates the user in Stash.

Step 1 — READ. When composing the agent's context for a turn, fetch that
user's memory and put it in the system prompt:
   POST /api/v1/me/vfs
   Header "Authorization: Bearer $STASH_API_KEY", body
   {"script": "cat /memory/*", "user_id": "<user>"}
   stdout is markdown: the shared wiki every user's agent reads.
   Also available on the same call: "cat /files/notepad/*" (this user's
   own wiki), "ls /sessions" and "cat /sessions/<id>" (their raw
   transcripts). Reading has nothing to do with which conversation you
   are in — no session id involved.

Step 2 — RECORD. After each turn (or batched later from a queue),
upload it:
   POST /api/v1/me/sessions/events/batch
   Header "Authorization: Bearer $STASH_API_KEY", body
   {"events": [{"agent_name": "<our agent>",
     "event_type": "user_message" | "assistant_message",
     "content": "...", "session_id": "<user>:<conversation>",
     "user_id": "<user>", "user_name": "<display name>"}]}
   session_id is ours to choose but must be unique across ALL our users
   — prefix it with the user id — and must not contain "/".

Step 3 — BACKFILL what we already have. Find where our database stores
past conversations and upload them through the same batch endpoint, one
session per conversation, with two extra rules:
   - Set created_at on every event to the turn's ORIGINAL timestamp
     (ISO 8601) so transcripts read in order.
   - Batch a few hundred events per request, skip empty content, and
     record progress (e.g. last uploaded conversation id) — re-running
     a session's upload appends duplicates, so the script must be
     resumable, not re-runnable from zero.
   Print a summary: users seen, sessions uploaded, events uploaded.
   If there is no existing history, say so and skip this step.

Step 4 — verify end to end. Send one message through the app and
confirm the user appears on the Users page of our Stash developer
console. Then tell me you're done — I'll press Backfill on the console's
Curator page so the curator reads everything, history included, and
builds each user's wiki plus the shared one.`;

export const BACKFILL_PROMPT = `Stash (https://api.joinstash.ai) is already wired into this app — this
task only loads our existing conversation history into it, so our
agent's memory covers everything from before the integration.

Context:
- Our Stash API key is in $STASH_API_KEY. It can read and record, never delete.
- Every event names the end user it belongs to via user_id — our own id for
  that customer, the same one we use on live traffic. First sight of a new
  user_id creates the user in Stash.

Steps:
1. Find where our database stores conversations (messages/turns, whatever
   they're called here) and how they group into a conversation per user.
2. For each conversation, POST its turns to
   /api/v1/me/sessions/events/batch with header
   "Authorization: Bearer $STASH_API_KEY" and body
   {"events": [{"agent_name": "<our agent>", "event_type": "user_message" |
   "assistant_message", "content": "...", "session_id": "<user>:<conversation>",
   "user_id": "<user>", "user_name": "<display name>",
   "created_at": "<the turn's ORIGINAL timestamp, ISO 8601>"}]}.
3. Rules that matter:
   - session_id must be unique across ALL our users — prefix it with the
     user id, and never put "/" in it.
   - Keep original timestamps so transcripts read in order; batch a few
     hundred events per request; skip empty content.
   - Re-running a session's upload appends duplicates — record progress
     (e.g. last uploaded conversation id) so the backfill is resumable.
4. Print a summary: users seen, sessions uploaded, events uploaded.

When it finishes, tell me — I'll press Backfill in the Stash console
(Curator page) so the curator reads the whole history and builds each
user's wiki plus the shared one.`;
