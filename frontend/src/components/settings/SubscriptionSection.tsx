"use client";

import { useEffect, useState } from "react";
import {
  BillingInfo,
  getBilling,
  openBillingPortal,
  redeemCode,
  startCheckout,
  setOverageLimit,
} from "../../lib/api";

export default function SubscriptionSection() {
  const [billing, setBilling] = useState<BillingInfo | null>(null);
  const [previewPlan, setPreviewPlan] = useState<BillingInfo["plan"] | null>(null);
  const [limitDollars, setLimitDollars] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getBilling()
      .then((info) => {
        setBilling(info);
        setLimitDollars(String(info.overage_limit_cents / 100));
      })
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
  const tokenLimit = isPro ? billing.pro_included_tokens : billing.free_included_tokens;
  const dollars = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

  async function saveLimit() {
    const amount = Number(limitDollars);
    if (!limitDollars.trim() || !Number.isFinite(amount) || amount < 0 || amount > 1000) {
      setError("Enter a monthly limit between $0 and $1,000.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setBilling(await setOverageLimit(Math.round(amount * 100)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update your spending limit");
    } finally {
      setBusy(false);
    }
  }

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
            ? "Enterprise includes custom transcript usage terms."
            : isPro
              ? `${tokenLimit.toLocaleString()} transcript tokens included each month, plus optional usage billing.`
              : `${tokenLimit.toLocaleString()} transcript tokens included each month for Skills curation.`}
        </p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-foreground">
            {isEnterprise ? "Enterprise" : isPro ? "Pro — $20/month" : "Free"}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {isEnterprise
              ? `${billing.transcript_tokens.toLocaleString()} transcript tokens curated this month.`
              : isPro
                ? `${billing.transcript_tokens.toLocaleString()} tokens curated this month; ${tokenLimit.toLocaleString()} included.`
                : `${billing.transcript_tokens.toLocaleString()} of ${tokenLimit.toLocaleString()} included tokens used this month.`}
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

      <div className="space-y-2 border-t border-border pt-3 text-xs text-muted-foreground">
        <p>
          New transcript text counts once when curation processes it. Uploading,
          searching, rereading, and retries add no usage charges.
        </p>
        <p>
          Allowances reset on {new Date(billing.resets_at).toLocaleDateString("en-US", {
            timeZone: "UTC", month: "long", day: "numeric",
          })} at 00:00 UTC. Unused tokens do not roll over.
        </p>
        {!isEnterprise && billing.remaining_tokens === 0 && (
          <p className="text-foreground">Curation is paused until your allowance resets or you increase your limit.</p>
        )}
        {isPro && (
          <p>
            Additional usage: {dollars.format(billing.overage_cents_per_million / 100)} per
            million transcript tokens. Estimated usage charges this month: {dollars.format(billing.overage_cents / 100)} before tax.
          </p>
        )}
        {isPro && billing.billing_enabled && billing.status === "active" && (
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              void saveLimit();
            }}
          >
            <label className="flex items-center gap-2 text-foreground">
              Monthly overage spending limit ($)
              <input
                aria-label="Monthly overage spending limit in dollars"
                type="number"
                min="0"
                max="1000"
                step="0.01"
                value={limitDollars}
                onChange={(event) => setLimitDollars(event.target.value)}
                className="w-24 rounded border border-border bg-background px-2 py-1"
              />
            </label>
            <p>
              $0 disables overages. Saving a positive limit authorizes usage charges up
              to that amount each UTC calendar month, before tax, in addition to your
              subscription. Curation pauses before exceeding it. Usage is invoiced
              monthly, including on annual plans.
            </p>
            <p>
              {billing.overages_enabled ? "Overages enabled." : "Overages disabled."} Already
              incurred charges remain payable if you lower the limit.
            </p>
            <button
              type="submit"
              disabled={busy}
              className="rounded border border-border px-3 py-1.5 text-foreground disabled:opacity-60"
            >
              {busy ? "Saving…" : "Save spending limit"}
            </button>
          </form>
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
