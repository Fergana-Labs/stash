"use client";

import CopyButton from "../../_components/CopyButton";
import type { PasteVisibility } from "../actions";

interface Props {
  slug: string;
  editToken: string;
  visibility: PasteVisibility;
  onReset: () => void;
}

// The shown-once panel after publishing: the public view link and the
// private edit link. The edit URL is the only place the token ever
// appears, so this panel is the one chance to save it.
export default function PublishedPanel({ slug, editToken, visibility, onReset }: Props) {
  const origin = window.location.origin;
  const viewUrl = `${origin}/pages/${slug}`;
  const editUrl = `${viewUrl}/edit?token=${editToken}`;

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <h2 className="font-display text-[20px] font-semibold text-ink">Your page is live.</h2>
      <div className="mt-4 space-y-3">
        <UrlRow label="View" hint="share this" url={viewUrl} />
        <UrlRow label="Edit" hint="keep this private" url={editUrl} />
      </div>
      <p className="mt-3 text-[13px] text-dim">
        {visibility === "unlisted"
          ? "Unlisted — anyone with the view link can read it, but it won't appear in the feed."
          : "Anyone with the view link can read it."}{" "}
        <span className="font-medium text-brand-ink">
          The edit link is the only way to change this page and won&apos;t be shown again.
        </span>
      </p>
      <div className="mt-5 flex items-center gap-4">
        <a
          href={viewUrl}
          className="inline-flex h-10 items-center rounded-md bg-brand px-4 text-[14px] font-medium text-white transition hover:bg-brand-hover"
        >
          View your page →
        </a>
        <button type="button" onClick={onReset} className="text-[14px] text-dim hover:text-ink">
          Publish another
        </button>
      </div>
    </div>
  );
}

function UrlRow({ label, hint, url }: { label: string; hint: string; url: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 font-mono text-[12px] text-muted">
        {label}
        <span className="block text-[10px] text-muted/80">{hint}</span>
      </span>
      <input
        type="text"
        readOnly
        value={url}
        onFocus={(e) => e.target.select()}
        className="h-9 min-w-0 flex-1 rounded-md border border-border bg-white px-3 font-mono text-[12px] text-ink"
      />
      <CopyButton
        value={url}
        className="inline-flex h-9 shrink-0 items-center rounded-md border border-border bg-white px-3 text-[13px] font-medium text-ink transition hover:bg-raised"
      />
    </div>
  );
}
