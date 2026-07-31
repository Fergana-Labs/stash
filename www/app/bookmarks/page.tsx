import type { Metadata } from "next";
import Link from "next/link";

import CtaPair from "../_components/CtaPair";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";

export const metadata: Metadata = {
  title: "Everything you've read, in one place your agent can use · Stash",
  description:
    "Stash captures what you read — articles, bookmarks, X threads, PDFs, AI chats — and what you saved and never got to. So your agent can find it, remember it, and act on it.",
};

// The three things having your reading in one place actually buys you. This is
// the spine of the page: capture is the mechanism, not the pitch.
const VERBS = [
  [
    "Find it",
    "“Which article had the bit about migration locks?” You read it, you can't name it, and search engines only know the open web. Stash answers from the thing you actually read, and links back to it.",
  ],
  [
    "Remember it",
    "You shouldn't have to remember that you read something in order to use it. Ask a question and what you read eight months ago comes back at the moment it's relevant — not when you happen to think of it.",
  ],
  [
    "Act on it",
    "Draft the reply, compare the two vendors, plan the trip — grounded in your own reading instead of a generic answer scraped off the web this morning.",
  ],
];

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
          <p className="kicker rise-in mb-6">Everything.you.read</p>
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            Your agent should know{" "}
            <span className="text-brand">everything you&apos;ve read.</span>
          </h1>
          <p className="mt-7 max-w-[640px] text-[18px] leading-[1.55] text-foreground">
            You&apos;ve read thousands of articles, threads, and PDFs this year.
            Your AI has read none of them. Stash captures what you read — and
            the pile you saved and never got to — so your agent can find it,
            remember it, and act on it.
          </p>
          <div className="mt-9">
            <CtaPair />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Saving was never the point.
          </h2>
          <p className="mt-5 max-w-[620px] text-[16px] leading-[1.6] text-dim">
            Every bookmark manager ends the story at &ldquo;saved.&rdquo; That&apos;s
            where this one starts.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-3">
            {VERBS.map(([name, blurb]) => (
              <div
                key={name}
                className="rounded-[12px] border border-border bg-background p-6 transition-colors hover:border-brand"
              >
                <div className="font-display text-[19px] font-bold tracking-[-0.01em] text-ink">
                  {name}
                </div>
                <p className="mt-2 text-[14.5px] leading-[1.55] text-dim">{blurb}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-16">
            <div>
              <p className="kicker">The.unread.pile</p>
              <h2 className="mt-5 text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
                And the things you haven&apos;t read.
              </h2>
              <p className="mt-5 text-[16px] leading-[1.6] text-foreground">
                The 200 links you saved and never opened are read on the way in
                anyway — the whole page, not the title. So the pile stops being
                a guilt trip and starts being a corpus: ask which of the forty
                things you saved this month actually answer your question, and
                skip the thirty-seven that don&apos;t.
              </p>
            </div>
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
            Getting it in takes one click. Usually zero.
          </h2>
          <p className="mt-5 max-w-[620px] text-[16px] leading-[1.6] text-dim">
            A library only works if filling it is free. Nothing here asks you to
            file, tag, or tidy.
          </p>
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
          <div className="mt-12 max-w-[900px]">
            <Shot
              src="/screens/save-page.jpg"
              caption="One click from the browser extension, on any page you're reading."
            />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="kicker">Not.a.notebook</p>
          <h2 className="mt-5 max-w-[820px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            A library that fills itself, not a notebook you fill by hand.
          </h2>
          <p className="mt-6 max-w-[680px] text-[16px] leading-[1.6] text-foreground">
            Gemini Notebook — the tool formerly called NotebookLM — is grounded
            in sources you hand it, one notebook at a time, capped at 50 sources
            per notebook on the free plan, with no way to ask across notebooks.
            That&apos;s a good way to study a stack of documents you&apos;ve
            already gathered. It isn&apos;t a way to know everything you read
            this year.
          </p>
          <p className="mt-4 max-w-[680px] text-[16px] leading-[1.6] text-foreground">
            Stash collects in the background instead: one library with no
            notebook walls around it, and a CLI, MCP server, and API so any
            agent you already use — Claude, ChatGPT, Cursor — can read the whole
            thing.
          </p>
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
