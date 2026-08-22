"use client";

import { useState } from "react";
import { Copy } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { mintDeveloperKey } from "@/lib/api";

/**
 * The standard two-step key dialog (the shape Anthropic's console uses):
 * "Create API key" with a name field, then "Save your API key" with the key
 * shown once over Copy key / Done. The name is required — a workspace full of
 * keys all called "production" is a workspace where nothing can be safely
 * revoked.
 *
 * The dialog portals to <body>, outside the console's data-surface wrapper,
 * so it re-declares data-surface="developer" to keep the console's tokens.
 */
// What the Expires select offers; "0" encodes "never" since select values are
// strings.
const EXPIRY_OPTIONS = [
  { value: "0", label: "Never" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "365", label: "1 year" },
];

export default function MintKeyDialog({ onMinted }: { onMinted: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [expiryDays, setExpiryDays] = useState(0);
  const [minting, setMinting] = useState(false);
  const [minted, setMinted] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cleared on every transition — open or close, trigger or Done button —
  // so no path can reopen onto a stale minted key.
  function reset(nextOpen: boolean) {
    setOpen(nextOpen);
    setName("");
    setExpiryDays(0);
    setMinted(null);
    setExpiresAt(null);
    setCopied(false);
    setError(null);
  }

  async function mint(e: React.FormEvent) {
    e.preventDefault();
    setMinting(true);
    setError(null);
    try {
      const res = await mintDeveloperKey(name.trim(), expiryDays || null);
      setMinted(res.api_key);
      setExpiresAt(res.expires_at);
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
          Create API key
        </button>
      </DialogTrigger>
      <DialogContent
        data-surface="developer"
        showCloseButton={!minted}
        className="rounded-xl bg-base p-8 sm:max-w-xl"
      >
        {minted ? (
          <>
            <DialogTitle className="font-display text-[26px] font-semibold tracking-tight text-foreground">
              Save your API key
            </DialogTitle>
            <p className="text-[15px] leading-7 text-muted-foreground">
              {expiresAt && (
                <>
                  This key expires on{" "}
                  <span className="font-medium text-foreground">{formatExpiry(expiresAt)}</span>
                  .{" "}
                </>
              )}
              Keep a record of the key below.{" "}
              <span className="font-medium text-foreground">
                You won&apos;t be able to view it again.
              </span>
            </p>
            <code className="block rounded-lg border border-border bg-surface px-4 py-3.5 font-mono text-[13px] leading-6 break-all text-foreground">
              {minted}
            </code>
            <div className="mt-2 flex justify-end gap-2.5">
              <button
                onClick={copy}
                className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-[14px] font-medium text-foreground transition-colors hover:bg-raised"
              >
                <Copy className="h-4 w-4" />
                {copied ? "Copied" : "Copy key"}
              </button>
              <button
                onClick={() => reset(false)}
                className="rounded-lg bg-brand-500 px-5 py-2.5 text-[14px] font-medium text-white transition-colors hover:bg-brand-600"
              >
                Done
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={mint} className="grid gap-4">
            <DialogTitle className="font-display text-[26px] font-semibold tracking-tight text-foreground">
              Create API key
            </DialogTitle>
            <div>
              <label htmlFor="mint-key-name" className="text-[15px] font-medium text-foreground">
                Name
              </label>
              <input
                id="mint-key-name"
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="production-backend"
                maxLength={128}
                className="mt-2 w-full rounded-lg border border-border bg-base px-4 py-3 text-[15px] text-foreground placeholder:text-muted-foreground focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none"
              />
              <p className="mt-2 text-[13px] leading-5 text-muted-foreground">
                Reads the knowledge base and records sessions — never deletes or rewrites.
              </p>
            </div>
            <div>
              <label htmlFor="mint-key-expiry" className="text-[15px] font-medium text-foreground">
                Expires
              </label>
              <Select
                id="mint-key-expiry"
                value={String(expiryDays)}
                onChange={(v) => setExpiryDays(Number(v))}
                options={EXPIRY_OPTIONS}
                className="mt-2 w-full rounded-lg px-4 py-3 text-[15px]"
              />
            </div>
            {error && <p className="text-[13px] text-error">{error}</p>}
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={minting || !name.trim()}
                className="rounded-lg bg-brand-500 px-5 py-2.5 text-[14px] font-medium text-white transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-muted-foreground/30 disabled:text-white"
              >
                {minting ? "Adding…" : "Add"}
              </button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function formatExpiry(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
