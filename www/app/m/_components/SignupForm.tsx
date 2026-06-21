"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import CustomSelect from "../../_components/CustomSelect";
import { submitVariantSignup, type VariantSignupState } from "../actions";
import { LANDING_URL_KEY } from "./CaptureLanding";

const INITIAL_STATE: VariantSignupState = { status: "idle" };

const USAGE_OPTIONS = ["Daily", "Weekly", "Occasionally", "Not yet"];

const REFERRAL_SOURCES = [
  "X / Twitter",
  "Search engine",
  "LinkedIn",
  "Hacker News",
  "GitHub",
  "From a colleague",
  "Podcast or newsletter",
  "Other",
];

const USE_CASES = [
  "Shared context for my team's agents",
  "Store & search agent-generated docs",
  "Connect agents to my tools (Slack, GitHub, Drive…)",
  "Publish & share agent work",
];

// Sign-up flow for the /m/[variant] message-test pages. Submissions email
// the team tagged with the message variant so we can rank which positioning
// converts.
export default function SignupForm({
  variant,
  appUrl,
}: {
  variant: string;
  appUrl: string;
}) {
  const [state, formAction] = useActionState(submitVariantSignup, INITIAL_STATE);
  const [agentUsage, setAgentUsage] = useState("");
  const [referralSource, setReferralSource] = useState("");

  // The landing page recorded its full URL (with the ad's utm params) in
  // sessionStorage — document.referrer is blank after Next's client-side
  // navigation. Falls back to the referrer for direct hits on this page.
  function submitWithRef(formData: FormData) {
    formData.set(
      "ref",
      sessionStorage.getItem(LANDING_URL_KEY) || document.referrer,
    );
    formAction(formData);
  }

  if (state.status === "ok") {
    return (
      <div
        className="mt-10 rounded-[14px] border border-border bg-background p-8 text-center"
        style={{ boxShadow: "var(--shadow-card)" }}
      >
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-brand">
          You&apos;re signed up
        </p>
        <h2 className="mt-3 font-display text-[28px] font-bold tracking-[-0.02em] text-ink">
          Welcome to Stash.
        </h2>
        <p className="mt-3 text-[15px] leading-[1.6] text-dim">
          We&apos;ll reach out within a day to get you set up. You can also jump
          straight in:
        </p>
        <a
          href={appUrl}
          className="mt-6 inline-flex h-11 items-center rounded-lg bg-brand px-5 text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover"
        >
          Create your account now →
        </a>
      </div>
    );
  }

  return (
    <form
      action={submitWithRef}
      className="mt-10 flex flex-col gap-5 rounded-[14px] border border-border bg-background p-7"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <input type="hidden" name="variant" value={variant} />

      <div className="flex flex-col gap-2">
        <label
          htmlFor="email"
          className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
        >
          Work email<span className="ml-1 text-brand">*</span>
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          className="h-11 rounded-lg border border-border bg-surface px-3 text-[14px] text-ink outline-none transition focus:border-ink"
        />
      </div>

      <div className="flex flex-col gap-2">
        <label
          htmlFor="roleCompany"
          className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
        >
          Role &amp; company
        </label>
        <input
          id="roleCompany"
          name="roleCompany"
          type="text"
          placeholder="e.g. Founder at Acme"
          className="h-11 rounded-lg border border-border bg-surface px-3 text-[14px] text-ink outline-none transition focus:border-ink"
        />
      </div>

      <div className="flex flex-col gap-2">
        <label
          htmlFor="referralSource"
          className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
        >
          How did you find us?
        </label>
        <CustomSelect
          id="referralSource"
          name="referralSource"
          value={referralSource}
          options={[
            { value: "", label: "Select…" },
            ...REFERRAL_SOURCES.map((s) => ({ value: s, label: s })),
          ]}
          onChange={setReferralSource}
        />
      </div>

      <div className="flex flex-col gap-2">
        <label
          htmlFor="agentUsage"
          className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
        >
          Do you use AI coding agents (Claude Code, Cursor…)?
        </label>
        <CustomSelect
          id="agentUsage"
          name="agentUsage"
          value={agentUsage}
          options={[
            { value: "", label: "Select…" },
            ...USAGE_OPTIONS.map((o) => ({ value: o, label: o })),
          ]}
          onChange={setAgentUsage}
        />
      </div>

      <fieldset className="flex flex-col gap-2.5">
        <legend className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          What would you use Stash for?
        </legend>
        {USE_CASES.map((useCase) => (
          <label
            key={useCase}
            className="flex cursor-pointer items-center gap-3 text-[14px] leading-[1.4] text-ink"
          >
            <input
              type="checkbox"
              name="useCases"
              value={useCase}
              className="h-4 w-4 shrink-0 cursor-pointer accent-[var(--brand)]"
            />
            {useCase}
          </label>
        ))}
        <textarea
          name="otherUseCase"
          rows={2}
          placeholder="Anything else?"
          className="mt-1 rounded-lg border border-border bg-surface px-3 py-2.5 text-[14px] leading-[1.55] text-ink outline-none transition focus:border-ink"
        />
      </fieldset>

      {state.status === "error" && state.message ? (
        <p className="rounded-md border border-[rgba(220,38,38,0.3)] bg-[rgba(220,38,38,0.06)] px-3 py-2 text-[13px] text-[#B91C1C]">
          {state.message}
        </p>
      ) : null}

      <SubmitButton />
    </form>
  );
}

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="inline-flex h-11 items-center justify-center rounded-lg bg-brand px-[18px] text-[14px] font-medium text-white shadow-sm transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pending ? "Signing up…" : "Sign up"}
    </button>
  );
}
