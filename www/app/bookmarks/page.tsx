import type { Metadata } from "next";
import Link from "next/link";

import CtaPair from "../_components/CtaPair";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";

export const metadata: Metadata = {
  alternates: { canonical: "/bookmarks" },
  title: "AI-native bookmarks · Stash",
  description:
    "Give your agents a personal internet filled with all the best things you've opened, or never got around to, on the inter-webs. Clip anything, keep it in a private library, and let your existing agents use it right away.",
};

// Kept in sync by hand with the same constant in the app's /extension page —
// www and frontend are separate deployables and share no module.
const CHROME_WEB_STORE_URL =
  "https://chromewebstore.google.com/detail/stash-sync/cggimcbkomkpielefiannhmenmoehbea";

// Verbatim from the in-app /extension page, so the two surfaces say the same thing.
const CLIPS = [
  ["Clip any page", "Articles, PDFs, and every open tab. Saved clean and readable."],
  ["Bring your bookmarks", "Import the whole file. We fetch what's behind every link."],
  ["Twitter bookmarks", "Your X bookmarks, synced. Text, images, and threads kept."],
  ["AI chats", "ChatGPT and Claude, streamed in. Searchable like everything else."],
];

export default function BookmarksPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader />

      <section className="relative overflow-hidden border-b border-border-subtle py-24 md:py-32">
        <Texture className="h-[560px]" fade="top" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 z-0 h-[520px]"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 18% 8%, rgba(249,115,22,0.10), transparent 60%)",
          }}
        />
        <div className="relative z-10 mx-auto max-w-[1200px] px-7">
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            Give your agents a{" "}
            <span className="text-brand">personal internet.</span>
          </h1>
          <p className="mt-7 max-w-[640px] text-[18px] leading-[1.55] text-foreground">
            Filled with all the best things you&apos;ve opened, or never got
            around to, on the inter-webs. Relax knowing that even if you
            don&apos;t get to something, your agent will.
          </p>
          <div className="mt-9">
            <CtaPair />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Save anything from the web.
          </h2>

          <a
            href={CHROME_WEB_STORE_URL}
            target="_blank"
            rel="noopener"
            className="mt-7 inline-flex h-11 items-center rounded-lg border border-ink bg-background px-5 text-[14px] font-semibold text-ink transition hover:bg-raised"
          >
            Add to Chrome — it&apos;s free
          </a>

          <div className="mt-12 max-w-[980px]">
            <Shot
              src="/screens/save-page.webp"
              width={1440}
              height={620}
              alt="The Stash Sync extension popup open on a Wikipedia article, offering Save this tab and Save all open tabs."
            />
          </div>

          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {CLIPS.map(([name, blurb]) => (
              <div
                key={name}
                className="rounded-[12px] border border-border bg-background p-5 transition-colors hover:border-brand"
              >
                <div className="font-display text-[16px] font-bold tracking-[-0.01em] text-ink">
                  {name}
                </div>
                <p className="mt-1.5 text-[14px] leading-[1.55] text-dim">{blurb}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[860px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            We maintain a private library and build an LLM wiki of key topics.
          </h2>

          <div className="mt-12">
            <Shot
              src="/screens/bookmarks-table.webp"
              width={1600}
              height={732}
              alt="The Stash bookmarks table: title, URL, type, saved date, and site for each clip, with a detail panel showing one bookmark's summary and topics."
            />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[860px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Your existing agents use Stash to get context right away.
          </h2>

          <div className="mt-12">
            <Shot
              src="/screens/agent-context.webp"
              width={1600}
              height={1318}
              alt="A coding agent answering a question about continual learning from saved papers, citing specific arXiv IDs and results."
            />
          </div>

          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href="/docs/quickstart"
              className="inline-flex h-10 items-center rounded-lg border border-border bg-background px-4 text-[13.5px] font-medium text-ink transition hover:border-ink"
            >
              Quickstart →
            </Link>
            <Link
              href="/docs/cli"
              className="inline-flex h-10 items-center rounded-lg border border-border bg-background px-4 text-[13.5px] font-medium text-ink transition hover:border-ink"
            >
              CLI reference
            </Link>
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden py-28 text-center">
        <Texture className="opacity-70" fade="center" />
        <div className="relative z-10 mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-bold leading-[1.0] tracking-[-0.035em] text-ink">
            You did the reading. Get to keep it.
          </h2>
          <div className="mt-8 flex justify-center">
            <CtaPair align="center" />
          </div>
          <Link
            href="/drive"
            className="mt-6 inline-flex font-mono text-[13px] text-dim transition hover:text-brand"
          >
            See the Drive it all lands in →
          </Link>
        </div>
      </section>
    </main>
  );
}

function Shot({
  src,
  alt,
  width,
  height,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
}) {
  return (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading="lazy"
      className="w-full rounded-xl border border-border shadow-[var(--shadow-card)]"
    />
  );
}
