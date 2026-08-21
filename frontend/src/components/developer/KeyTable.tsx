"use client";

import { useCallback, useEffect, useState } from "react";
import { KeyRound } from "lucide-react";

import { listDeveloperKeys, revokeDeveloperKey, type DeveloperKey } from "@/lib/api";

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString() : "never";
}

/**
 * The workspace's active keys — name, access, age, last use, revoke. Key
 * material never appears here: a key is shown once, at mint time. `refresh`
 * bumps when a key is minted so the new row shows up without a reload.
 */
export default function KeyTable({ refresh }: { refresh: number }) {
  const [keys, setKeys] = useState<DeveloperKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Two-click revoke: the first click arms this row, the second commits.
  // An inline confirm rather than a browser dialog, matching the console.
  const [arming, setArming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listDeveloperKeys()
      .then((res) => setKeys(res.keys))
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load keys"));
  }, []);

  useEffect(() => {
    load();
  }, [load, refresh]);

  async function revoke(id: string) {
    setBusy(true);
    setError(null);
    try {
      await revokeDeveloperKey(id);
      setArming(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not revoke the key");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="text-[14px] text-error">{error}</p>;
  if (keys === null) return <p className="text-[14px] text-muted-foreground">Loading…</p>;
  if (keys.length === 0) {
    return (
      <p className="rounded border border-dashed border-border px-6 py-8 text-center text-[15px] leading-7 text-muted-foreground">
        No active keys. Mint one below — it is shown once, then only its name lives here.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded border border-border bg-surface">
      {keys.map((key) => (
        <div
          key={key.id}
          className="flex items-center gap-4 border-b border-border px-5 py-4 last:border-b-0"
        >
          <KeyRound className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[15px] font-medium text-foreground">
              {key.name}
            </span>
            <span className="mt-0.5 block truncate font-mono text-[12px] text-muted-foreground">
              created {when(key.created_at)} · last used {when(key.last_used_at)}
            </span>
          </span>
          <span
            className={
              key.access === "full"
                ? "shrink-0 rounded-full bg-brand-500/12 px-2.5 py-0.5 text-[12px] font-medium text-brand-600"
                : "shrink-0 rounded-full bg-raised px-2.5 py-0.5 text-[12px] font-medium text-dim"
            }
          >
            {key.access === "full" ? "Full access" : "Read + record"}
          </span>
          {arming === key.id ? (
            <span className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => void revoke(key.id)}
                disabled={busy}
                className="rounded-sm bg-error px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Revoking…" : "Confirm revoke"}
              </button>
              <button
                onClick={() => setArming(null)}
                disabled={busy}
                className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised"
              >
                Keep
              </button>
            </span>
          ) : (
            <button
              onClick={() => setArming(key.id)}
              className="shrink-0 rounded-sm border border-border px-3 py-1.5 text-[13px] text-dim transition-colors hover:bg-raised hover:text-error"
            >
              Revoke
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
