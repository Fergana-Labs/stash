"use client";

import { Code, CodeBlock, SectionHeading } from "@/components/developer/DocsPrimitives";

const READ = `# Your agent reads. tenant_id is the only thing Stash needs — it is
# the isolation boundary. No session, no conversation: reading memory has
# nothing to do with which conversation you are in.
curl -X POST https://api.joinstash.ai/api/v1/me/vfs \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"script":"cat /memory/*", "tenant_id":"org_acme"}'`;

const WRITE = `# Your backend uploads transcripts. Its own mechanism — after the
# turn, in a batch, from a queue worker, whenever suits you.
curl -X POST https://api.joinstash.ai/api/v1/me/sessions/events/batch \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"events":[{"agent_name":"my-agent","event_type":"user_message",
       "content":"...","session_id":"org_acme:conv-123",
       "tenant_id":"org_acme","tenant_name":"Acme Trucks"}]}'`;

/** The two-call integration contract. */
export default function SetupCard() {
  return (
    <>
      <div className="mt-12">
        <SectionHeading>Reading: what your agent sees</SectionHeading>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          One field. <Code>tenant_id</Code> is your own id for that user, and it is the
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
          not a security boundary — <Code>tenant_id</Code> is. It groups turns into one
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
    </>
  );
}
