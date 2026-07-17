import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { SSR_BACKEND_ORIGIN } from "@/lib/backendOrigin";
import { PageBody } from "../../skills/[slug]/SkillItemBodies";

interface PublicPaste {
  slug: string;
  title: string;
  content_type: "markdown" | "html";
  content: string;
  view_count: number;
  created_at: string;
  updated_at: string;
}

// cache() so generateMetadata and the page share one fetch per request —
// the backend increments view_count on every read.
const loadPaste = cache(async (slug: string): Promise<PublicPaste | null> => {
  const res = await fetch(`${SSR_BACKEND_ORIGIN}/api/v1/pastes/${encodeURIComponent(slug)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
});

type PageProps = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const paste = await loadPaste(slug);
  if (!paste) return { title: "Page - Stash" };
  return { title: `${paste.title || "Untitled"} - Stash` };
}

/** In-app viewer for a community page (pastebin paste) — public, like /skills/[slug]. */
export default async function CommunityPage({ params }: PageProps) {
  const { slug } = await params;
  const paste = await loadPaste(slug);
  if (!paste) notFound();

  return (
    <div className="mx-auto max-w-[860px] px-6 py-10">
      <h1 className="font-display text-[28px] font-bold leading-tight text-foreground">
        {paste.title || "Untitled"}
      </h1>
      <p className="mt-1.5 text-[12.5px] text-muted-foreground">
        Community page · {paste.view_count} view{paste.view_count === 1 ? "" : "s"}
      </p>
      <div className="mt-8">
        <PageBody
          page={{
            id: paste.slug,
            name: paste.title || "Untitled",
            content_type: paste.content_type,
            content_markdown: paste.content_type === "markdown" ? paste.content : "",
            content_html: paste.content_type === "html" ? paste.content : "",
            html_layout: "responsive",
            updated_at: paste.updated_at,
            folder_path: [],
          }}
        />
      </div>
    </div>
  );
}
