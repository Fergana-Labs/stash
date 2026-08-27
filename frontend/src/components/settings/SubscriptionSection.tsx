"use client";

import { useEffect, useState } from "react";
import {
  BillingInfo,
  getBilling,
  openBillingPortal,
  redeemCode,
  startCheckout,
} from "../../lib/api";

export default function SubscriptionSection() {
  const [billing, setBilling] = useState<BillingInfo | null>(null);
  const [previewPlan, setPreviewPlan] = useState<BillingInfo["plan"] | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getBilling()
      .then(setBilling)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load billing"))
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) {
    return <p className="text-sm text-muted-foreground">Loading subscription…</p>;
  }

  if (error && !billing) {
    return <p className="text-sm text-error">{error}</p>;
  }

  if (!billing) {
    throw new Error("Billing settings loaded without billing information");
  }

  const canPreview = !billing.billing_enabled && process.env.NODE_ENV === "development";
  const plan = previewPlan ?? billing.plan;
  const isPro = plan === "pro";
  const isEnterprise = plan === "enterprise";
  const curatedTraces = billing.curated_trace_count ?? 0;
  const traceLimit = isPro
    ? billing.pro_curated_trace_limit
    : billing.free_curated_trace_limit;

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
    <section className="space-y-3 rounded-lg border border-border bg-surface p-5">
      {canPreview && (
        <div className="flex items-center justify-between gap-4 border-b border-border pb-3">
          <div>
            <div className="text-xs font-medium text-foreground">Local plan preview</div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">
              This UI is so you can debug the plan screen even when running stash locally.
            </div>
          </div>
          <div className="flex rounded-md border border-border bg-background p-0.5">
            {(["free", "pro", "enterprise"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setPreviewPlan(option)}
                className={`cursor-pointer rounded px-2.5 py-1 text-xs capitalize ${
                  plan === option
                    ? "bg-raised font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      )}
      <div>
        <h2 className="text-base font-semibold text-foreground">Plan</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {isEnterprise
            ? "Enterprise includes uncapped Skill creation."
            : isPro
              ? "Stash supports Skill creation from up to 10,000 traces per month on the Pro plan."
              : "Stash supports Skill creation from up to 1,000 traces on the free plan."}
        </p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-foreground">
            {isEnterprise ? "Enterprise" : isPro ? "Pro — $20/month" : "Free"}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {isEnterprise
              ? "Granted plan — Skill creation is uncapped."
              : isPro
                ? `${curatedTraces.toLocaleString()} of ${traceLimit.toLocaleString()} traces curated this month.`
                : `${curatedTraces.toLocaleString()} of ${traceLimit.toLocaleString()} free traces curated.`}
          </div>
        </div>
        {isEnterprise ? null : canPreview ? (
          <PlanActionPreview isPro={isPro} />
        ) : !billing.billing_enabled ? (
          <span className="text-xs text-muted-foreground">
            Billing is not configured for this installation.
          </span>
        ) : isPro ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => redirectTo(openBillingPortal)}
            className="cursor-pointer rounded-md border border-border px-3 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:bg-raised disabled:opacity-60"
          >
            {busy ? "Opening…" : "Manage subscription"}
          </button>
        ) : (
          <div className="flex flex-col items-end gap-1.5">
            <button
              type="button"
              disabled={busy}
              onClick={() => redirectTo(() => startCheckout("month"))}
              className="cursor-pointer rounded-md border border-border bg-background px-3 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:bg-raised disabled:opacity-60"
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
      {billing.billing_enabled && (
        <p className="text-[11px] text-muted-foreground">
          Plan changes can take a few seconds to apply after checkout.
        </p>
      )}
    </section>
  );
}

function PlanActionPreview({ isPro }: { isPro: boolean }) {
  if (isPro) {
    return (
      <div className="flex flex-col items-end gap-1">
        <span className="rounded-md border border-border px-3 py-1.5 text-[13px] font-medium text-foreground">
          Manage subscription
        </span>
        <span className="text-[11px] text-muted-foreground">Preview only</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1.5">
      <span className="rounded-md border border-border bg-background px-3 py-1.5 text-[13px] font-medium text-foreground">
        Upgrade — $20/month
      </span>
      <span className="text-xs text-muted-foreground underline">
        or $200/year — 2 months free
      </span>
      <span className="text-[11px] text-muted-foreground no-underline">Preview only</span>
    </div>
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
          className="w-48 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-brand focus:outline-none"
        />
        <button
          type="button"
          onClick={() => void apply()}
          disabled={submitting || !code.trim()}
          className="cursor-pointer rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-raised disabled:opacity-60"
        >
          {submitting ? "Applying…" : "Apply"}
        </button>
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  );
}
