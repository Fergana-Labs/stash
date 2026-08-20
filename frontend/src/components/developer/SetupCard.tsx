"use client";

import { useState } from "react";

import { Code, CodeBlock, SectionHeading } from "@/components/developer/DocsPrimitives";
import { mintDeveloperKey } from "@/lib/api";

const READ = `# Your agent reads. org_id is the only thing Stash needs — it is
# the isolation boundary. No session, no conversation: reading memory has
# nothing to do with which conversation you are in.
curl -X POST https://api.joinstash.ai/api/v1/me/vfs \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"script":"cat /memory/*", "org_id":"org_acme"}'`;

const WRITE = `# Your backend uploads transcripts. Its own mechanism — after the
# turn, in a batch, from a queue worker, whenever suits you.
curl -X POST https://api.joinstash.ai/api/v1/me/sessions/events/batch \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"events":[{"agent_name":"my-agent","event_type":"user_message",
       "content":"...","session_id":"org_acme:conv-123",
       "org_id":"org_acme","org_name":"Acme Trucks"}]}'`;

/** Key minting plus the two-call integration contract. */
export default function SetupCard() {
  const [minted, setMinted] = useState<string | null>(null);
  const [minting, setMinting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function mint() {
    setMinting(true);
    setError(null);
    try {
      const res = await mintDeveloperKey("production");
      setMinted(res.api_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not mint a key");
    } finally {
      setMinting(false);
    }
  }

  function copy() {
    if (!minted) return;
    navigator.clipboard.writeText(minted);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <>
      {minted ? (
        <div className="flex items-center gap-3 rounded border border-border bg-surface px-5 py-4">
          <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-foreground">
            {minted}
          </code>
          <button
            onClick={copy}
            className="shrink-0 rounded-sm border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised hover:text-foreground"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      ) : (
        <button
          onClick={mint}
          disabled={minting}
          className="rounded-sm bg-brand-500 px-4 py-2 text-[14px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
        >
          {minting ? "Minting…" : "Mint an API key"}
        </button>
      )}
      {error && <p className="mt-3 text-[14px] text-error">{error}</p>}

      <div className="mt-12">
        <SectionHeading>Reading: what your agent sees</SectionHeading>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          One field. <Code>org_id</Code> is your own id for that customer, and it is the
          isolation boundary: the shared wiki at <Code>/memory</Code>, that customer&apos;s
          notepad and files under <Code>/files</Code>, their transcripts under{" "}
          <Code>/sessions</Code>, and nothing of anyone else&apos;s. First time we see an id,
          the org is created.
        </p>
        <div className="mt-5">
          <CodeBlock>{READ}</CodeBlock>
        </div>
      </div>

      <div className="mt-12">
        <SectionHeading>Uploading: recording what happened</SectionHeading>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          A separate mechanism, and the only place a <Code>session_id</Code> appears. It is
          not a security boundary — <Code>org_id</Code> is. It groups turns into one
          transcript, which is what the curator learns from.
        </p>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          Session ids are yours to choose, and must be unique across all of your customers —
          two customers sending <Code>conv-1</Code> is refused, rather than filing one
          customer&apos;s turn inside the other&apos;s transcript. Prefix them with the
          customer, and not with <Code>/</Code>: a slash makes the transcript unreadable,
          since the id is a path parameter on those endpoints.
        </p>
        <div className="mt-5">
          <CodeBlock>{WRITE}</CodeBlock>
        </div>
      </div>

    </>
  );
}
