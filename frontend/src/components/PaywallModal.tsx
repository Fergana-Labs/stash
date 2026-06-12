"use client";

import { useState } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { startCheckout } from "../lib/api";

// Shown when the backend returns 402 on a connect attempt: the free plan's
// one-source limit is hit and adding more requires Pro.
export default function PaywallModal({ onClose }: { onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEscapeKey(true, onClose);

  async function upgrade(interval: "month" | "year") {
    setBusy(true);
    setError("");
    try {
      const { url } = await startCheckout(interval);
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start checkout");
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 px-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Upgrade to Pro"
        className="w-full max-w-sm rounded-xl border border-border bg-base p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-[14px] font-semibold text-foreground">
          Upgrade to Pro
        </div>
        <div className="mt-1.5 text-[12.5px] leading-[1.55] text-muted">
          The free plan includes 1 connected source. Pro unlocks unlimited
          connected sources — GitHub, Slack, Gmail, Drive, Notion, and more —
          for $20/month.
        </div>
        {error && <div className="mt-2 text-[12px] text-error">{error}</div>}
        <div className="mt-4 flex items-center justify-end gap-1.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised"
          >
            Not now
          </button>
          <button
            type="button"
            autoFocus
            disabled={busy}
            onClick={() => upgrade("month")}
            className="rounded-md bg-brand px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:opacity-60"
          >
            {busy ? "Redirecting…" : "Upgrade — $20/month"}
          </button>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => upgrade("year")}
          className="mt-2 block w-full text-right text-[11.5px] text-muted underline hover:text-foreground disabled:opacity-60"
        >
          or $200/year — 2 months free
        </button>
      </div>
    </div>
  );
}
