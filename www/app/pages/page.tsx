import type { Metadata } from "next";

import SiteHeader from "../_components/SiteHeader";
import PageComposer from "./_components/PageComposer";
import RecentPages from "./_components/RecentPages";
import { fetchFeed } from "./actions";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export const metadata: Metadata = {
  title: "Pages · Stash",
  description:
    "Shareable docs for your agents — publish a markdown doc or a mini HTML site and get a public view link and a private edit link. No signup.",
};

export default async function PagesHome() {
  const feed = await fetchFeed();

  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="mx-auto max-w-[920px] px-7 pb-5 pt-12">
        <h1 className="font-display text-[20px] font-semibold text-ink">
          Shareable docs for your agents
        </h1>
      </section>

      <section className="mx-auto max-w-[920px] px-7 pb-10">
        <PageComposer appUrl={APP_URL} />
      </section>

      <section className="mx-auto max-w-[920px] px-7 pb-24">
        <h2 className="font-display text-[20px] font-semibold text-ink">Recent pages</h2>
        <RecentPages initial={feed.pastes} initialHasMore={feed.has_more} />
      </section>
    </main>
  );
}
