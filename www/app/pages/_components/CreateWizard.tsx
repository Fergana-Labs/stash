"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import type { PasteContentType, PasteVisibility } from "../actions";

type VisibilityChoice = PasteVisibility | "private";

// The create flow's front door: pick what you're making and who can see
// and edit it, then open the full editor at /pages/new. "Private" is the
// signup gate — anonymous pages can't be private, that's the product.
export default function CreateWizard({ appUrl }: { appUrl: string }) {
  const router = useRouter();
  const [type, setType] = useState<PasteContentType | null>(null);
  const [visibility, setVisibility] = useState<VisibilityChoice>("public");
  const [publicEdit, setPublicEdit] = useState(false);

  const isPrivate = visibility === "private";
  const canContinue = type !== null && !isPrivate;

  function openEditor() {
    if (!canContinue || !type) return;
    router.push(`/pages/new?type=${type}&visibility=${visibility}&editable=${publicEdit}`);
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-5 sm:p-6">
      <StepLabel n={1}>What are you making?</StepLabel>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <ChoiceCard
          selected={type === "markdown"}
          onSelect={() => setType("markdown")}
          title="Markdown page"
          description="A document — notes, a README, a blog post. Rich-text editor included."
          badge="MD"
        />
        <ChoiceCard
          selected={type === "html"}
          onSelect={() => setType("html")}
          title="HTML site"
          description="A mini site with its own styles and scripts, rendered as-is."
          badge="HTML"
        />
      </div>

      <StepLabel n={2} className="mt-6">
        Who can see it?
      </StepLabel>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <ChoiceCard
          selected={visibility === "public"}
          onSelect={() => setVisibility("public")}
          title="Public"
          description="Shows in the feed below."
        />
        <ChoiceCard
          selected={visibility === "unlisted"}
          onSelect={() => setVisibility("unlisted")}
          title="Unlisted"
          description="Only people with the link."
        />
        <ChoiceCard
          selected={isPrivate}
          onSelect={() => setVisibility("private")}
          title="Private 🔒"
          description="Only you. Needs an account."
        />
      </div>

      <StepLabel n={3} className="mt-6">
        Who can edit it?
      </StepLabel>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <ChoiceCard
          selected={!publicEdit}
          onSelect={() => setPublicEdit(false)}
          title="Only me"
          description="You get a secret edit link, shown once."
        />
        <ChoiceCard
          selected={publicEdit}
          onSelect={() => setPublicEdit(true)}
          title="Anyone with the link"
          description="The public link is also editable — a shared scratchpad."
        />
      </div>

      <div className="mt-6 flex items-center justify-between gap-4">
        {isPrivate ? (
          <>
            <p className="text-[13.5px] text-dim">
              Private pages live in your Stash workspace, with sharing controls and agent
              access.
            </p>
            <a
              href={appUrl}
              className="inline-flex h-10 shrink-0 items-center rounded-md bg-brand px-5 text-[14px] font-medium text-white transition hover:bg-brand-hover"
            >
              Start free →
            </a>
          </>
        ) : (
          <>
            <p className="text-[13.5px] text-muted">
              {type === null ? "Pick a page type to continue." : "No signup. Permanent link."}
            </p>
            <button
              type="button"
              onClick={openEditor}
              disabled={!canContinue}
              className="inline-flex h-10 shrink-0 items-center rounded-md bg-brand px-5 text-[14px] font-medium text-white transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              Open the editor →
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function StepLabel({
  n,
  children,
  className = "",
}: {
  n: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p className={`flex items-center gap-2 text-[14px] font-medium text-ink ${className}`}>
      <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-ink font-mono text-[11px] text-white">
        {n}
      </span>
      {children}
    </p>
  );
}

function ChoiceCard({
  selected,
  onSelect,
  title,
  description,
  badge,
}: {
  selected: boolean;
  onSelect: () => void;
  title: string;
  description: string;
  badge?: string;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={
        "rounded-lg border p-3.5 text-left transition " +
        (selected
          ? "border-brand bg-white ring-1 ring-brand"
          : "border-border bg-white hover:border-muted")
      }
    >
      <span className="flex items-center gap-2 text-[14.5px] font-medium text-ink">
        {title}
        {badge && (
          <span className="rounded border border-border bg-raised px-1.5 py-0.5 font-mono text-[10px] text-dim">
            {badge}
          </span>
        )}
      </span>
      <span className="mt-1 block text-[13px] leading-snug text-dim">{description}</span>
    </button>
  );
}
