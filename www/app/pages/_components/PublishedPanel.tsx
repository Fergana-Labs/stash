"use client";

import Link from "next/link";

import CopyButton from "../../_components/CopyButton";
import type { PasteVisibility } from "../actions";

interface Props {
  slug: string;
  editToken: string;
  visibility: PasteVisibility;
  publicEdit: boolean;
}

// The shown-once panel after publishing. The edit URL is the only place
// the edit token ever appears — when the page is publicly editable there
// is no token in the URL, the plain /edit route works for everyone.
export default function PublishedPanel({ slug, editToken, visibility, publicEdit }: Props) {
  const origin = window.location.origin;
  const viewUrl = `${origin}/pages/${slug}`;
  const editUrl = publicEdit ? `${viewUrl}/edit` : `${viewUrl}/edit?token=${editToken}`;
  const rawUrl = `${viewUrl}/raw`;

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <h2 className="font-display text-[20px] font-semibold text-ink">Your page is live.</h2>
      <p className="mt-1 text-[14px] text-dim">
        {visibility === "unlisted"
          ? "It's unlisted — only people with the link can find it."
          : "It's public — anyone with the link can see it, and it shows in the feed."}
        {publicEdit && " Anyone with the link can also edit it."}
      </p>
      <div className="mt-5 space-y-3">
        <UrlRow label="View" url={viewUrl} />
        <UrlRow label="Edit" url={editUrl} />
        <UrlRow label="Raw" url={rawUrl} />
      </div>
      {!publicEdit && (
        <p className="mt-3 text-[13px] font-medium text-brand-ink">
          Save the edit link — it&apos;s the only way to edit this page and it won&apos;t be
          shown again.
        </p>
      )}
      <div className="mt-5 flex items-center gap-4">
        <a
          href={viewUrl}
          className="inline-flex h-10 items-center rounded-md bg-brand px-4 text-[14px] font-medium text-white transition hover:bg-brand-hover"
        >
          View your page →
        </a>
        <Link href="/pages" className="text-[14px] text-dim hover:text-ink">
          Publish another
        </Link>
      </div>
    </div>
  );
}

function UrlRow({ label, url }: { label: string; url: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-10 shrink-0 font-mono text-[12px] text-muted">{label}</span>
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
