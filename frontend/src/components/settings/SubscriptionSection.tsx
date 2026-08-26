"use client";

import { useEffect, useState } from "react";
import { TEAMS_CONTACT_EMAIL } from "../../lib/contact";
import {
  BillingInfo,
  getBilling,
  openBillingPortal,
  redeemCode,
  startCheckout,
} from "../../lib/api";

// Renders nothing on self-hosted instances (billing_enabled false).
export default function SubscriptionSection() {
  const [billing, setBilling] = useState<BillingInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getBilling()
      .then(setBilling)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load billing"));
  }, []);

  if (!billing?.billing_enabled) return null;

  const isPro = billing.plan === "pro";
  const isEnterprise = billing.plan === "enterprise";

  async function redirectTo(action: () => Promise<{ url: string }>) {
    setBusy(true);
    setError("");
    try {
      const { url } = await action();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-foreground">Subscription</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Free includes {billing.connection_limit} connected source accounts and{" "}
          {billing.free_curator_runs_per_month} Memory-curator runs per month. Pro
          ($20/month) includes unlimited connected sources, unlimited curator runs, and
          the managed agent model — your agent runs without connecting a Claude, ChatGPT,
          or OpenRouter account of your own.
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Want a shared team workspace? Email{" "}
          <a className="underline" href={`mailto:${TEAMS_CONTACT_EMAIL}`}>
            {TEAMS_CONTACT_EMAIL}
          </a>
          .
        </p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-foreground">
            {isEnterprise ? "Enterprise" : isPro ? "Pro — $20/month" : "Free"}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {isEnterprise
              ? "Granted plan — integrations and curator runs are unlimited."
              : isPro
              ? `Subscription ${billing.status}.`
              : `${billing.connection_count} of ${billing.connection_limit} connected accounts used.`}
          </div>
        </div>
        {isEnterprise ? null : isPro ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => redirectTo(openBillingPortal)}
            className="cursor-pointer text-sm font-semibold px-4 py-2 rounded-lg border border-border text-foreground hover:bg-raised disabled:opacity-60 transition-colors"
          >
            {busy ? "Opening…" : "Manage subscription"}
          </button>
        ) : (
          <div className="flex flex-col items-end gap-1.5">
            <button
              type="button"
              disabled={busy}
              onClick={() => redirectTo(() => startCheckout("month"))}
              className="cursor-pointer bg-brand hover:bg-brand-hover disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
            >
              {busy ? "Redirecting…" : "Upgrade — $20/month"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => redirectTo(() => startCheckout("year"))}
              className="cursor-pointer text-xs text-muted-foreground hover:text-foreground underline disabled:opacity-60"
            >
              or $200/year — 2 months free
            </button>
          </div>
        )}
      </div>

      {!isPro && !isEnterprise && (
        <RedeemCodeRow onRedeemed={() => getBilling().then(setBilling).catch(() => {})} />
      )}

      {error && <p className="text-xs text-error">{error}</p>}
      <p className="text-[11px] text-muted-foreground">
        Plan changes can take a few seconds to apply after checkout.
      </p>
    </section>
  );
}

// A hackathon (or other) access code unlocks the granted plan without a card.
function RedeemCodeRow({ onRedeemed }: { onRedeemed: () => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function apply() {
    if (!code.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await redeemCode(code.trim());
      onRedeemed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That code didn't work");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="cursor-pointer text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
      >
        Have a hackathon or access code?
      </button>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void apply();
            }
          }}
          placeholder="Access code"
          autoFocus
          className="w-48 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-brand focus:outline-none"
        />
        <button
          type="button"
          onClick={() => void apply()}
          disabled={submitting || !code.trim()}
          className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-raised disabled:opacity-60"
        >
          {submitting ? "Applying…" : "Apply"}
        </button>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  );
}
