import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import HtmlPageView from "../../../../../components/workspace/HtmlPageView";

const BACKEND_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ pageId: string }>;
}): Promise<Metadata> {
  const { pageId } = await params;
  const page = await loadPage(pageId);
  if (!page) return { title: "Page not found · Stash" };
  const folder = page.folder_name ? ` · ${page.folder_name}` : "";
  const title = `${page.name}${folder} · Stash`;
  const description = page.folder_name
    ? `A page in folder "${page.folder_name}".`
    : "A page in Stash.";
  return {
    title,
    description,
    openGraph: { title, description, type: "article", siteName: "Stash" },
    twitter: { card: "summary", title, description },
  };
}

interface PublicPage {
  id: string;
  name: string;
  content_type: "markdown" | "html";
  content_markdown: string;
  content_html: string;
  html_layout: "responsive" | "fixed-aspect";
  folder_id: string | null;
  folder_name: string | null;
  workspace_id: string;
  updated_at: string;
}

async function loadPage(pageId: string): Promise<PublicPage | null> {
  const res = await fetch(`${BACKEND_ORIGIN}/api/v1/public/pages/${pageId}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`page fetch failed: ${res.status}`);
  return res.json();
}

export default async function PublicPageReader({
  params,
}: {
  params: Promise<{ workspaceId: string; pageId: string }>;
}) {
  const { workspaceId, pageId } = await params;
  const page = await loadPage(pageId);
  if (!page) notFound();

  return (
    <main className="mx-auto max-w-[860px] px-7 py-12">
      <nav className="font-mono text-[11px] uppercase tracking-wider text-muted">
        <Link href={`/s/${workspaceId}`} className="hover:text-ink">
          Workspace
        </Link>
        {page.folder_id && page.folder_name && (
          <>
            {" "}
            ›{" "}
            <Link href={`/s/${workspaceId}/f/${page.folder_id}`} className="hover:text-ink">
              {page.folder_name}
            </Link>
          </>
        )}
      </nav>

      <header className="mt-4 border-b border-border-subtle pb-6">
        <h1 className="font-display text-[clamp(28px,3vw,40px)] font-black leading-[1.1] tracking-[-0.02em] text-ink">
          {page.name}
        </h1>
      </header>

      <article className="mt-8">
        {page.content_type === "html" ? (
          <HtmlPageView
            html={page.content_html || ""}
            title={page.name}
            layout={page.html_layout}
          />
        ) : (
          <div className="markdown-content">
            <Markdown remarkPlugins={[remarkGfm]}>{page.content_markdown || "(empty)"}</Markdown>
          </div>
        )}
      </article>
    </main>
  );
}
