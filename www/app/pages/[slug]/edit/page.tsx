import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import HtmlEditWorkbench from "../../_components/HtmlEditWorkbench";
import MarkdownEditClient from "../../_components/MarkdownEditClient";
import { fetchPaste } from "../../_lib/paste";

export const metadata: Metadata = {
  title: "Edit page · Stash Pages",
  robots: { index: false },
};

type Params = Promise<{ slug: string }>;
type SearchParams = Promise<{ token?: string }>;

// The secret-link edit page. Markdown gets the Tiptap WYSIWYG editor
// full-page; HTML gets the View | Edit | Raw workbench. The token is only
// checked on save (a bad one surfaces as "Invalid edit link") — no eager
// validation endpoint to act as a token oracle.
export default async function PasteEditPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const { token } = await searchParams;
  const paste = await fetchPaste(slug);
  if (!paste || !token) notFound();

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center gap-x-4 gap-y-1 px-6 py-3">
          <Link href="/pages" className="font-mono text-[12px] text-muted hover:text-ink">
            stash pages
          </Link>
          <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium text-ink">
            Editing: {paste.title}
          </span>
          <Link
            href={`/pages/${paste.slug}`}
            className="shrink-0 text-[12.5px] font-medium text-dim hover:text-ink"
          >
            View page →
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-[1100px] px-6 py-6">
        {paste.content_type === "html" ? (
          <HtmlEditWorkbench
            slug={paste.slug}
            token={token}
            title={paste.title}
            initialHtml={paste.content}
          />
        ) : (
          <MarkdownEditClient slug={paste.slug} token={token} initialMarkdown={paste.content} />
        )}
      </div>
    </main>
  );
}
