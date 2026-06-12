import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import HtmlFrame from "../_components/HtmlFrame";
import MarkdownView from "../_components/MarkdownView";
import { fetchPaste } from "../_lib/paste";
import { timeAgo } from "../_lib/time";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

type Params = Promise<{ slug: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug } = await params;
  const paste = await fetchPaste(slug);
  if (!paste) return { title: "Page not found · Stash" };
  return {
    title: `${paste.title} · Stash Pages`,
    description: `A ${paste.content_type === "html" ? "mini site" : "page"} published on Stash Pages.`,
  };
}

// Public read page: render-only — no selector, no edit affordances.
// The secret edit link is the only path to editing.
export default async function PasteReadPage({ params }: { params: Params }) {
  const { slug } = await params;
  const paste = await fetchPaste(slug);
  if (!paste) notFound();

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center gap-x-4 gap-y-1 px-6 py-3">
          <Link href="/pages" className="font-mono text-[12px] text-muted hover:text-ink">
            stash pages
          </Link>
          <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium text-ink">
            {paste.title}
          </span>
          <span className="inline-flex shrink-0 rounded border border-border bg-white px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-dim">
            {paste.content_type === "markdown" ? "MD" : "HTML"}
          </span>
          {paste.visibility === "unlisted" && (
            <span className="inline-flex shrink-0 rounded border border-border bg-white px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-dim">
              unlisted
            </span>
          )}
          <span className="shrink-0 text-[12.5px] text-muted">{timeAgo(paste.created_at)}</span>
          <span className="shrink-0 text-[12.5px] text-muted">
            {paste.view_count} {paste.view_count === 1 ? "view" : "views"}
          </span>
          {paste.public_edit && (
            <Link
              href={`/pages/${paste.slug}/edit`}
              className="shrink-0 font-mono text-[12px] text-dim underline-offset-2 hover:text-ink hover:underline"
            >
              Edit
            </Link>
          )}
          <a
            href={`/pages/${paste.slug}/raw`}
            className="shrink-0 font-mono text-[12px] text-dim underline-offset-2 hover:text-ink hover:underline"
          >
            Raw
          </a>
        </div>
      </header>

      <div className="border-b border-border-subtle bg-raised/50">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-2 px-6 py-2">
          <p className="text-[12.5px] text-dim">
            This page is public — anyone with the link can see it.{" "}
            <a href={APP_URL} className="font-medium text-brand hover:underline">
              Sign up for Stash
            </a>{" "}
            to make it private.
          </p>
          <Link href="/pages" className="text-[12.5px] font-medium text-dim hover:text-ink">
            Create your own page →
          </Link>
        </div>
      </div>

      <div className="mx-auto max-w-[1100px] px-6 py-6">
        {paste.content_type === "html" ? (
          <div className="overflow-hidden rounded-xl border border-border bg-white">
            <HtmlFrame html={paste.content} title={paste.title} />
          </div>
        ) : (
          <MarkdownView content={paste.content} />
        )}
      </div>
    </main>
  );
}
