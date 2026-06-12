import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../_components/SiteHeader";
import AgentInstructions from "./_components/AgentInstructions";
import CreateWizard from "./_components/CreateWizard";
import { timeAgo } from "./_lib/time";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.joinstash.ai";
const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export const metadata: Metadata = {
  title: "Pages · Stash",
  description:
    "Publish a markdown doc or a mini HTML site in seconds. No signup — you get a public link, a secret edit link, and raw access for agents.",
};

type FeedPaste = {
  slug: string;
  title: string;
  content_type: "markdown" | "html";
  view_count: number;
  created_at: string;
};

async function fetchFeed(): Promise<FeedPaste[]> {
  const res = await fetch(`${API_URL}/api/v1/pastes`, { cache: "no-store" });
  if (!res.ok) return [];
  const body = await res.json();
  return body.pastes ?? [];
}

export default async function PagesHome() {
  const feed = await fetchFeed();

  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="mx-auto max-w-[920px] px-7 pb-10 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Pages
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(36px,4.6vw,56px)] font-black leading-[1.02] tracking-[-0.035em] text-ink">
          Publish a page.
          <br />
          <span className="text-brand">No signup.</span>
        </h1>
        <p className="mt-6 max-w-[640px] text-[17px] leading-[1.6] text-foreground">
          Write a markdown doc or a mini HTML site and get a permanent link, an edit link,
          and raw source access. Built for humans and agents alike.
        </p>
      </section>

      <section className="mx-auto max-w-[920px] px-7 pb-8">
        <CreateWizard appUrl={APP_URL} />
      </section>

      <section className="mx-auto max-w-[920px] px-7 pb-16">
        <AgentInstructions />
      </section>

      <section className="mx-auto max-w-[920px] px-7 pb-24">
        <h2 className="font-display text-[22px] font-semibold text-ink">Recent pages</h2>
        {feed.length === 0 ? (
          <p className="mt-4 text-[14px] text-muted">Nothing published yet — be the first.</p>
        ) : (
          <ul className="mt-4 divide-y divide-border-subtle rounded-xl border border-border bg-surface">
            {feed.map((paste) => (
              <li key={paste.slug}>
                <Link
                  href={`/pages/${paste.slug}`}
                  className="flex items-center gap-3 px-4 py-3 transition hover:bg-raised/60"
                >
                  <TypeBadge contentType={paste.content_type} />
                  <span className="min-w-0 flex-1 truncate text-[14.5px] font-medium text-ink">
                    {paste.title}
                  </span>
                  <span className="shrink-0 text-[12.5px] text-muted">
                    {paste.view_count} {paste.view_count === 1 ? "view" : "views"}
                  </span>
                  <span className="w-16 shrink-0 text-right text-[12.5px] text-muted">
                    {timeAgo(paste.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function TypeBadge({ contentType }: { contentType: "markdown" | "html" }) {
  return (
    <span className="inline-flex w-12 shrink-0 justify-center rounded border border-border bg-white px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-dim">
      {contentType === "markdown" ? "MD" : "HTML"}
    </span>
  );
}
