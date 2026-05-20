"use client";

import { useState } from "react";

import { ONBOARDING_TEMPLATES } from "@/lib/onboarding/templates";

type Props = {
  selected: Set<string>;
  onToggle: (slug: string) => void;
  busy: boolean;
  error: string | null;
};

export default function TemplatesStep({ selected, onToggle, busy, error }: Props) {
  if (ONBOARDING_TEMPLATES.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Start from a template
        </h1>
        <p className="text-sm text-dim">
          No templates available yet. Skip ahead — you can browse{" "}
          <a href="/discover" className="text-brand underline">
            Discover
          </a>{" "}
          for community Stashes anytime.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="font-display text-[28px] leading-[1.1] font-bold tracking-tight text-foreground">
          Start from a template
        </h1>
        <p className="text-sm text-dim max-w-md">
          Pick any starter Stashes you want — we&rsquo;ll copy them into your
          workspace so you have something to edit on day one.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {ONBOARDING_TEMPLATES.map((t) => {
          const isSelected = selected.has(t.slug);
          return (
            <Card
              key={t.slug}
              title={t.title}
              description={t.description}
              selected={isSelected}
              disabled={busy}
              onClick={() => onToggle(t.slug)}
            />
          );
        })}
      </div>

      <p className="text-[11px] text-muted">
        Templates are copied into your workspace. Edits stay yours — there&rsquo;s
        no sync from the original.
      </p>

      {error && (
        <div className="text-[12px] text-error rounded-lg border border-error/30 bg-error/10 px-3 py-2">
          {error}
        </div>
      )}
    </div>
  );
}

function Card({
  title,
  description,
  selected,
  disabled,
  onClick,
}: {
  title: string;
  description: string;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`text-left rounded-xl border p-4 transition-colors disabled:opacity-60 ${
        selected
          ? "border-brand bg-brand/5 ring-1 ring-brand"
          : "border-border bg-surface hover:bg-raised"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-[13px] font-semibold text-foreground">{title}</div>
        <span
          aria-hidden
          className={`h-4 w-4 rounded border flex items-center justify-center text-[10px] ${
            selected ? "border-brand bg-brand text-white" : "border-border bg-background"
          }`}
        >
          {selected ? "✓" : ""}
        </span>
      </div>
      <div className="mt-1 text-[12px] text-muted leading-relaxed">{description}</div>
    </button>
  );
}
