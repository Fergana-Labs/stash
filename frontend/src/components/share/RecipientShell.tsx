"use client";

import { useState } from "react";
import { shareForkStash, shareRequestEdit, type ShareProjection } from "../../lib/api";

interface RecipientShellProps {
  projection: ShareProjection;
  token: string;
  onPresent?: () => void;
  children: React.ReactNode;
}

function daysUntil(iso: string | null): string | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (ms < 0) return "expired";
  const days = Math.ceil(ms / (1000 * 60 * 60 * 24));
  return `${days} day${days === 1 ? "" : "s"}`;
}

export default function RecipientShell({
  projection,
  token,
  onPresent,
  children,
}: RecipientShellProps) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [email, setEmail] = useState("");

  const sharer =
    projection.stash?.creator.display_name ||
    projection.stash?.creator.name ||
    "Shared link";
  const expiry = daysUntil(projection.share.expires_at);

  async function fork() {
    setBusy(true);
    try {
      const ws = await shareForkStash(token);
      window.location.href = `/stashes/${ws.id}`;
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 401) {
        // Send through login then bounce back.
        const back = encodeURIComponent(window.location.pathname);
        window.location.href = `/login?next=${back}`;
        return;
      }
      setMsg(err.message || "Fork failed");
      setBusy(false);
    }
  }

  async function submitRequest() {
    setBusy(true);
    try {
      await shareRequestEdit(token, { email });
      setMsg("Edit request sent.");
      setShowRequestModal(false);
    } catch (e) {
      setMsg((e as Error).message || "Failed to send request");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <header className="border-b border-border-subtle bg-surface px-6 py-3">
          <div className="flex items-center gap-3">
            <span
              className="inline-flex h-8 w-8 items-center justify-center rounded-full font-display text-[12px] font-bold text-white"
              style={{ background: "var(--color-brand)" }}
            >
              {sharer[0]?.toUpperCase() || "?"}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] text-foreground">
                <strong>{sharer}</strong> shared this with you
              </div>
              <div className="text-[11px] text-muted">
                {projection.share.permission} · {expiry ? `expires in ${expiry}` : "no expiry"} ·{" "}
                {projection.share.view_count} view{projection.share.view_count === 1 ? "" : "s"}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowRequestModal(true)}
                className="rounded-md border border-border-subtle bg-base px-3 py-1.5 text-[12px] hover:border-brand hover:text-brand"
              >
                Request edit access
              </button>
              <button
                onClick={fork}
                disabled={busy}
                className="rounded-md border border-border-subtle bg-base px-3 py-1.5 text-[12px] hover:border-brand hover:text-brand"
              >
                Fork
              </button>
              {onPresent && (
                <button
                  onClick={onPresent}
                  className="rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-hover)]"
                >
                  Present →
                </button>
              )}
            </div>
          </div>
        </header>

        {msg && (
          <div className="border-b border-border-subtle bg-brand-muted px-6 py-2 text-[12px] text-foreground">
            {msg}
          </div>
        )}

        <div className="flex-1 px-8 py-8">{children}</div>

        {showRequestModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
            <div className="w-full max-w-sm rounded-2xl border border-border bg-base p-5 shadow-xl">
              <h3 className="font-display text-[15px] font-semibold text-foreground">
                Request edit access
              </h3>
              <p className="mt-1 text-[12px] text-muted">
                We&apos;ll send {sharer} a note that you want to edit this stash.
              </p>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                className="mt-3 w-full rounded-md border border-border bg-surface px-3 py-2 text-[13px] focus:border-brand focus:outline-none"
              />
              <div className="mt-4 flex justify-end gap-2">
                <button
                  onClick={() => setShowRequestModal(false)}
                  className="rounded-md px-3 py-1.5 text-[12px] text-muted hover:text-foreground"
                >
                  Cancel
                </button>
                <button
                  onClick={submitRequest}
                  disabled={busy}
                  className="rounded-md bg-brand px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-hover)] disabled:opacity-40"
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
