"use client";

import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { mintDeveloperKey } from "@/lib/api";

/**
 * The standard key-mint flow, in a dialog: name the key, mint it, copy it
 * once. The name is required — a workspace full of keys all called
 * "production" is a workspace where nothing can be safely revoked.
 */
export default function MintKeyDialog({ onMinted }: { onMinted: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [minting, setMinting] = useState(false);
  const [minted, setMinted] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset(nextOpen: boolean) {
    setOpen(nextOpen);
    if (nextOpen) {
      setName("");
      setMinted(null);
      setCopied(false);
      setError(null);
    }
  }

  async function mint(e: React.FormEvent) {
    e.preventDefault();
    setMinting(true);
    setError(null);
    try {
      const res = await mintDeveloperKey(name.trim());
      setMinted(res.api_key);
      onMinted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not mint a key");
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
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>
        <button className="rounded-sm bg-brand-500 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600">
          Mint an API key
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{minted ? "Your new key" : "Mint an API key"}</DialogTitle>
          <DialogDescription>
            {minted
              ? "Copy it now — this is the only time the full key is shown."
              : "The key your product's backend calls Stash with. It can read the knowledge base and record sessions, and can never delete or rewrite anything."}
          </DialogDescription>
        </DialogHeader>
        {minted ? (
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded border border-border bg-surface px-3 py-2 font-mono text-[12.5px] text-foreground">
              {minted}
            </code>
            <button
              onClick={copy}
              className="shrink-0 rounded-sm border border-border px-3 py-2 text-[13px] text-dim transition-colors hover:bg-raised hover:text-foreground"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        ) : (
          <form onSubmit={mint} className="flex items-center gap-2">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name it — production-backend, staging, ci"
              maxLength={128}
              className="min-w-0 flex-1 rounded border border-border bg-surface px-3 py-2 text-[14px] text-foreground placeholder:text-muted-foreground focus:border-brand-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={minting || !name.trim()}
              className="shrink-0 rounded-sm bg-brand-500 px-3.5 py-2 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
            >
              {minting ? "Minting…" : "Mint"}
            </button>
          </form>
        )}
        {error && <p className="text-[13px] text-error">{error}</p>}
      </DialogContent>
    </Dialog>
  );
}
