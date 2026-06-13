"use client";

import { useState } from "react";
import Link from "next/link";

import { loadMorePages, type FeedPaste } from "../actions";
import { timeAgo } from "../_lib/time";

// The Recent-pages feed list with offset "Load more" pagination — the
// initial page is server-rendered (small + fast), subsequent pages are
// fetched on demand through a server action so the browser never loads
// the whole feed up front.
export default function RecentPages({
  initial,
  initialHasMore,
}: {
  initial: FeedPaste[];
  initialHasMore: boolean;
}) {
  const [pages, setPages] = useState(initial);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [loading, setLoading] = useState(false);

  async function more() {
    if (loading) return;
    setLoading(true);
    const result = await loadMorePages(pages.length);
    setPages((cur) => [...cur, ...result.pastes]);
    setHasMore(result.has_more);
    setLoading(false);
  }

  if (pages.length === 0) {
    return <p className="mt-4 text-[14px] text-muted">Nothing published yet — be the first.</p>;
  }

  return (
    <>
      <ul className="mt-4 divide-y divide-border-subtle rounded-xl border border-border bg-surface">
        {pages.map((paste) => (
          <li key={paste.slug}>
            <Link
              href={`/pages/${paste.slug}`}
              className="flex items-center gap-3 px-4 py-3 transition hover:bg-raised/60"
            >
              <TypeBadge contentType={paste.content_type} />
              <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium text-ink">
                {paste.title}
              </span>
              <span className="w-16 shrink-0 text-right text-[12.5px] text-muted">
                {timeAgo(paste.created_at)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {hasMore && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={more}
            disabled={loading}
            className="inline-flex h-9 items-center rounded-md border border-border bg-white px-4 text-[13px] font-medium text-ink transition hover:bg-raised disabled:opacity-50"
          >
            {loading ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </>
  );
}

function TypeBadge({ contentType }: { contentType: "markdown" | "html" }) {
  return (
    <span className="inline-flex w-12 shrink-0 justify-center rounded border border-border bg-white px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-dim">
      {contentType === "markdown" ? "MD" : "HTML"}
    </span>
  );
}
