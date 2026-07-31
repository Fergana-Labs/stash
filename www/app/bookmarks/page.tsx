import type { Metadata } from "next";
import Link from "next/link";

import CtaPair from "../_components/CtaPair";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";

export const metadata: Metadata = {
  title: "A bookmark manager that read the bookmarks · Stash",
  description:
    "Clip any page, import your whole bookmarks file, and sync your X bookmarks. Stash keeps the page itself — text, images, PDFs — so you can ask what it said months later.",
};

const SAVES = [
  [
    "Clip any page",
    "One click saves the page you're reading — or every open tab — as a clean, readable copy. PDFs included.",
  ],
  [
    "Import your bookmarks",
    "Bring your whole bookmarks file. Stash fetches each page's content in the background, so a dead link still has the article behind it.",
  ],
  [
    "Twitter bookmarks",
    "Your X bookmarks sync automatically — text, images, and threads archived so they outlive the post.",
  ],
  [
    "AI chats",
    "ChatGPT and Claude conversations stream in as transcripts, searchable next to everything else you've saved.",
  ],
];

const KEEPS = [
  [
    "It keeps the page, not the link",
    "A saved link is a promise the site will still be up. Stash stores the whole text, the images, and the PDF, so a dead URL still has the article behind it.",
  ],
  [
    "Ask, don't dig",
    "Search by meaning, not title. Ask what you saved about a topic six months ago and get the answer with links back to the source.",
  ],
  [
    "It organizes itself",
    "Saved pages get titles, summaries, and tags on the way in. The pile stays browsable without you filing anything.",
  ],
  [
    "Your AI reads it too",
    "Everything you save lands in the same Drive your agents work from — so the answer comes from what you actually read, not from the open web.",
  ],
];

function Shot({ src, caption }: { src: string; caption: string }) {
  return (
    <figure>
      <img
        src={src}
        alt={caption}
        className="w-full rounded-xl border border-border shadow-[var(--shadow-card)]"
      />
      <figcaption className="mt-3 text-[13.5px] leading-[1.55] text-dim">{caption}</figcaption>
    </figure>
  );
}

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
          <p className="kicker rise-in mb-6">Bookmark.manager</p>
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            A bookmark manager{" "}
            <span className="text-brand">that read the bookmarks.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            You save things all day — tabs, bookmarks, X threads — into places
            you never look at again. Stash keeps the page itself, so months
            later you can ask what it said instead of hoping the site is still
            up.
          </p>
          <div className="mt-9">
            <CtaPair />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-16 md:py-20">
        <div className="mx-auto max-w-[1200px] px-7">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
            <Shot
              src="/screens/save-page.jpg"
              caption="One click from the browser extension, on any page you're reading."
            />
            <Shot
              src="/screens/bookmarks-library.jpg"
              caption="Everything you've saved in one library — filterable, sortable, kept in full."
            />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Saving to it takes one click. Usually zero.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {SAVES.map(([name, blurb]) => (
              <div
                key={name}
                className="rounded-[12px] border border-border bg-background p-5 transition-colors hover:border-brand"
              >
                <div className="font-display text-[17px] font-bold tracking-[-0.01em] text-ink">
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
          <h2 className="max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Then it does what a folder of links can&apos;t.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {KEEPS.map(([name, blurb]) => (
              <div
                key={name}
                className="rounded-[12px] border border-border bg-background p-5 transition-colors hover:border-brand"
              >
                <div className="font-display text-[17px] font-bold tracking-[-0.01em] text-ink">
                  {name}
                </div>
                <p className="mt-1.5 text-[14px] leading-[1.55] text-dim">{blurb}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden py-28 text-center">
        <Texture className="opacity-70" fade="center" />
        <div className="relative z-10 mx-auto max-w-[1200px] px-7">
          <h2 className="text-balance font-display text-[clamp(36px,4.6vw,64px)] font-bold leading-[1.0] tracking-[-0.035em] text-ink">
            Stop saving things you&apos;ll never find again.
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
