"use client";

import { useState } from "react";

import { Code, CodeBlock, SectionHeading } from "@/components/developer/DocsPrimitives";

const READ = `# Your agent reads. user_id is the only thing Stash needs — it is
# the isolation boundary. No session, no conversation: reading memory has
# nothing to do with which conversation you are in.
curl -X POST https://api.joinstash.ai/api/v1/me/vfs \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"script":"cat /memory/*", "user_id":"user_sam"}'`;

const WRITE = `# Your backend uploads transcripts. Its own mechanism — after the
# turn, in a batch, from a queue worker, whenever suits you.
curl -X POST https://api.joinstash.ai/api/v1/me/sessions/events/batch \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"events":[{"agent_name":"my-agent","event_type":"user_message",
       "content":"...","session_id":"user_sam:conv-123",
       "user_id":"user_sam","user_name":"Sam Ellery"}]}'`;

// The backfill prompt is written for the developer's coding agent, not for a
// human: paste it into Claude Code / Cursor pointed at their codebase and it
// has everything it needs — endpoint, payload shape, and the rules that are
// easy to get wrong (id uniqueness, original timestamps, batching).
const BACKFILL_PROMPT = `Write and run a one-time backfill that uploads our existing conversation
history into Stash (https://api.joinstash.ai), so our agent's memory starts
from our full history instead of empty.

Context:
- Our Stash API key is in $STASH_API_KEY. It can read and record, never delete.
- Every event names the end user it belongs to via user_id — our own id for
  that customer, the same one we'll use on live traffic. First sight of a new
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

/** The two-call integration contract, plus the backfill your history path. */
export default function SetupCard() {
  return (
    <>
      <div className="mt-12">
        <SectionHeading>Reading: what your agent sees</SectionHeading>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          One field. <Code>user_id</Code> is your own id for that user, and it is the
          isolation boundary: the shared wiki at <Code>/memory</Code>, that user&apos;s
          wiki and files under <Code>/files</Code>, their raw transcripts under{" "}
          <Code>/sessions</Code>, and nothing of anyone else&apos;s. First time we see an id,
          the user is created.
        </p>
        <div className="mt-5">
          <CodeBlock>{READ}</CodeBlock>
        </div>
      </div>

      <div className="mt-12">
        <SectionHeading>Uploading: recording what happened</SectionHeading>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          A separate mechanism, and the only place a <Code>session_id</Code> appears. It is
          not a security boundary — <Code>user_id</Code> is. It groups turns into one
          transcript, which is what the curator learns from.
        </p>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          Session ids are yours to choose, and must be unique across all of your users —
          two users sending <Code>conv-1</Code> is refused, rather than filing one
          user&apos;s turn inside the other&apos;s transcript. Prefix them with the
          user, and not with <Code>/</Code>: a slash makes the transcript unreadable,
          since the id is a path parameter on those endpoints.
        </p>
        <div className="mt-5">
          <CodeBlock>{WRITE}</CodeBlock>
        </div>
      </div>

      <BackfillPrompt />
    </>
  );
}

function BackfillPrompt() {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(BACKFILL_PROMPT);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="mt-12">
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading>Backfilling: start from your history</SectionHeading>
        <button
          onClick={copy}
          className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised hover:text-foreground"
        >
          {copied ? "Copied" : "Copy prompt"}
        </button>
      </div>
      <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
        You already have months of conversations in your own database. Paste this prompt
        into your coding agent, pointed at your codebase — it writes the one-time script
        that uploads them, and tells you when to press Backfill on the Curator page so the
        wikis build from day one.
      </p>
      <div className="mt-5">
        <CodeBlock>{BACKFILL_PROMPT}</CodeBlock>
      </div>
    </div>
  );
}
