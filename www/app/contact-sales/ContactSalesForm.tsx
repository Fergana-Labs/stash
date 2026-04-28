"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { submitContactSales, type ContactSalesState } from "./actions";

const INITIAL_STATE: ContactSalesState = { status: "idle" };

const TEAM_SIZES = ["1–5", "6–20", "21–50", "51–200", "200+"];

export default function ContactSalesForm() {
  const [state, formAction] = useActionState(submitContactSales, INITIAL_STATE);

  if (state.status === "ok") {
    return (
      <div
        className="rounded-[14px] border border-border bg-background p-8 text-center"
        style={{ boxShadow: "var(--shadow-card)" }}
      >
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-brand">
          Request received
        </p>
        <h2 className="mt-3 font-display text-[28px] font-bold tracking-[-0.02em] text-ink">
          We&apos;ll be in touch soon.
        </h2>
        <p className="mt-3 text-[15px] leading-[1.6] text-dim">{state.message}</p>
      </div>
    );
  }

  return (
    <form
      action={formAction}
      className="flex flex-col gap-5 rounded-[14px] border border-border bg-background p-7"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <Field label="Name" name="name" autoComplete="name" required />
      <Field
        label="Work email"
        name="email"
        type="email"
        autoComplete="email"
        required
      />
      <Field label="Company" name="company" autoComplete="organization" />

      <div className="flex flex-col gap-2">
        <label
          htmlFor="teamSize"
          className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
        >
          Team size
        </label>
        <select
          id="teamSize"
          name="teamSize"
          defaultValue=""
          className="h-11 rounded-lg border border-border bg-surface px-3 text-[14px] text-ink outline-none transition focus:border-ink"
        >
          <option value="">Select…</option>
          {TEAM_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-2">
        <label
          htmlFor="message"
          className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
        >
          What are you hoping to do with Stash?
        </label>
        <textarea
          id="message"
          name="message"
          rows={5}
          placeholder="A few sentences about your team and what you're trying to solve."
          className="rounded-lg border border-border bg-surface px-3 py-2.5 text-[14px] leading-[1.55] text-ink outline-none transition focus:border-ink"
        />
      </div>

      {state.status === "error" && state.message ? (
        <p className="rounded-md border border-[rgba(220,38,38,0.3)] bg-[rgba(220,38,38,0.06)] px-3 py-2 text-[13px] text-[#B91C1C]">
          {state.message}
        </p>
      ) : null}

      <SubmitButton />
      <p className="text-[12.5px] leading-[1.55] text-muted">
        Prefer email? Reach us at{" "}
        <a
          href="mailto:hi@ferganalabs.com"
          className="text-brand transition hover:underline"
        >
          hi@ferganalabs.com
        </a>
        .
      </p>
    </form>
  );
}

function Field({
  label,
  name,
  type = "text",
  autoComplete,
  required,
}: {
  label: string;
  name: string;
  type?: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={name}
        className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted"
      >
        {label}
        {required ? <span className="ml-1 text-brand">*</span> : null}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required={required}
        className="h-11 rounded-lg border border-border bg-surface px-3 text-[14px] text-ink outline-none transition focus:border-ink"
      />
    </div>
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
      {pending ? "Sending…" : "Book a demo"}
    </button>
  );
}
