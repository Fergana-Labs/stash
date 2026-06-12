"use client";

import { useEffect, useState } from "react";
import {
  BillingInfo,
  getBilling,
  openBillingPortal,
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
        <p className="text-xs text-muted mt-0.5">
          The free plan includes 1 connected account. Pro is $20/month for unlimited integrations.
        </p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-foreground">
            {isPro ? "Pro — $20/month" : "Free"}
          </div>
          <div className="text-xs text-muted mt-0.5">
            {isPro
              ? `Subscription ${billing.status}.`
              : `${billing.connection_count} of ${billing.connection_limit} connected account used.`}
          </div>
        </div>
        {isPro ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => redirectTo(openBillingPortal)}
            className="text-sm font-semibold px-4 py-2 rounded-lg border border-border text-foreground hover:bg-raised disabled:opacity-60 transition-colors"
          >
            {busy ? "Opening…" : "Manage subscription"}
          </button>
        ) : (
          <div className="flex flex-col items-end gap-1.5">
            <button
              type="button"
              disabled={busy}
              onClick={() => redirectTo(() => startCheckout("month"))}
              className="bg-brand hover:bg-brand-hover disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
            >
              {busy ? "Redirecting…" : "Upgrade — $20/month"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => redirectTo(() => startCheckout("year"))}
              className="text-xs text-muted hover:text-foreground underline disabled:opacity-60"
            >
              or $200/year — 2 months free
            </button>
          </div>
        )}
      </div>

      {error && <p className="text-xs text-error">{error}</p>}
      <p className="text-[11px] text-muted">
        Plan changes can take a few seconds to apply after checkout.
      </p>
    </section>
  );
}
