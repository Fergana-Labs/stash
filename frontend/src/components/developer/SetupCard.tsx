"use client";

import { useState } from "react";

import { Code, CodeBlock, SectionHeading } from "@/components/developer/DocsPrimitives";
import { mintDeveloperKey } from "@/lib/api";

const INTEGRATION = `# write: one event per turn, org_id names your customer
curl -X POST https://api.joinstash.ai/api/v1/me/sessions/events/batch \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"events":[{"agent_name":"my-agent","event_type":"user_message",
       "content":"...","session_id":"conv-123",
       "org_id":"org_acme","org_name":"Acme Trucks"}]}'

# read: the same org_id scopes the tree to that customer
curl -X POST https://api.joinstash.ai/api/v1/me/vfs \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"script":"cat /memory/*", "org_id":"org_acme"}'`;

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
        <SectionHeading>Two calls integrate Stash</SectionHeading>
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-dim">
          Upload each turn with your customer&apos;s <Code>org_id</Code>, then read with the
          same <Code>org_id</Code> to get that org&apos;s view: the shared wiki at{" "}
          <Code>/memory</Code>, its notepad and files under <Code>/files</Code>, its
          transcripts under <Code>/sessions</Code>.
        </p>
        <div className="mt-5">
          <CodeBlock>{INTEGRATION}</CodeBlock>
        </div>
      </div>
    </>
  );
}
