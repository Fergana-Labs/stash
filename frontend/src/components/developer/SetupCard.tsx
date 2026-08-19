"use client";

import { useState } from "react";
import { Check, Copy, KeyRound } from "lucide-react";

import { mintDeveloperKey } from "@/lib/api";

/** Key minting plus the two-call integration contract. */
export default function SetupCard() {
  const [minted, setMinted] = useState<string | null>(null);
  const [minting, setMinting] = useState(false);
  const [copied, setCopied] = useState(false);

  async function mint() {
    setMinting(true);
    try {
      const res = await mintDeveloperKey("production");
      setMinted(res.api_key);
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
    <div className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4">
      {minted ? (
        <div className="flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded bg-zinc-50 px-2 py-1 text-xs">
            {minted}
          </code>
          <button
            onClick={copy}
            className="flex items-center gap-1 rounded-md border border-zinc-200 px-2 py-1 text-xs hover:bg-zinc-50"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      ) : (
        <button
          onClick={mint}
          disabled={minting}
          className="flex items-center gap-2 rounded-md border border-zinc-200 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50"
        >
          <KeyRound className="h-4 w-4" />
          {minting ? "Minting…" : "Mint an API key"}
        </button>
      )}
      <p className="text-xs text-zinc-500">
        Two calls integrate Stash: upload each turn with your customer&apos;s{" "}
        <code>org_id</code>, and read with the same <code>org_id</code> to get
        that org&apos;s view (shared wiki at <code>/memory</code>, its notepad
        and files under <code>/files</code>, its transcripts under{" "}
        <code>/sessions</code>).
      </p>
      <pre className="overflow-x-auto rounded bg-zinc-50 p-3 text-[11px] leading-relaxed">
        {`# write: one event per turn, org_id names your customer
curl -X POST https://api.joinstash.ai/api/v1/me/sessions/events/batch \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"events":[{"agent_name":"my-agent","event_type":"user_message",
       "content":"...","session_id":"conv-123",
       "org_id":"org_acme","org_name":"Acme Trucks"}]}'

# read: the same org_id scopes the tree to that customer
curl -X POST https://api.joinstash.ai/api/v1/me/vfs \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"script":"cat /memory/*", "org_id":"org_acme"}'`}
      </pre>
    </div>
  );
}
