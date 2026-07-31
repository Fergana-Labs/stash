import type { Metadata } from "next";
import Link from "next/link";

import CtaPair from "../_components/CtaPair";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";

export const metadata: Metadata = {
  title: "An AI-native Google Drive · Stash",
  description:
    "Your files and folders, in a Drive your AI can actually read. Real Markdown, HTML, CSV, and PDF, mounted as a filesystem any agent can ls, find, and rg.",
};

const DRIVE = [
  [
    "Real files, real folders",
    "Upload anything. Markdown, HTML, CSV, PDF, images — stored as files in folders you can move and rename, not rows in someone's database.",
  ],
  [
    "Your AI can read it",
    "The whole Drive mounts as a filesystem your agent can ls, find, and rg — through the CLI, the MCP server, or the API. Point Claude, ChatGPT, or Cursor at it and it works from your actual files.",
  ],
  [
    "Ask, don't dig",
    "Search by meaning, not filename. Ask what you wrote about a topic six months ago and get the answer, with links back to the file it came from.",
  ],
  [
    "Edit it together",
    "You and your AI edit the same file at the same time, two cursors at once. When it writes a page, you fix the wording by hand — no copy-paste round trip.",
  ],
  [
    "Your existing accounts",
    "Connect Gmail, Google Drive, and Notion. Stash reads them in place — nothing to migrate, nothing to re-file.",
  ],
  [
    "Share a link",
    "Any file or folder gets a public URL when you want one, and stays private when you don't.",
  ],
];

export default function DrivePage() {
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
          <p className="kicker rise-in mb-6">Your.drive</p>
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            An AI-native <span className="text-brand">Google Drive.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            Your files sit in a folder your AI can&apos;t open. Stash is a Drive
            built the other way round: real files in real folders, mounted as a
            filesystem any agent can read, search, and write back into.
          </p>
          <div className="mt-9">
            <CtaPair />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle py-16 md:py-20">
        <div className="mx-auto max-w-[1000px] px-7">
          <figure>
            <img
              src="/screens/drive.jpg"
              alt="The Stash Drive: folders in the explorer on the left, a Markdown note open and rendered on the right."
              className="w-full rounded-xl border border-border shadow-[var(--shadow-card)]"
            />
            <figcaption className="mt-3 text-[13.5px] leading-[1.55] text-dim">
              Folders on the left, the file open on the right — and the same tree mounted as a
              filesystem your agent reads.
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <h2 className="max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            A Drive that speaks your AI&apos;s language.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {DRIVE.map(([name, blurb]) => (
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
            Give your AI something to work from.
          </h2>
          <div className="mt-8 flex justify-center">
            <CtaPair align="center" />
          </div>
          <Link
            href="/bookmarks"
            className="mt-6 inline-flex font-mono text-[13px] text-dim transition hover:text-brand"
          >
            Saving pages, not files? See the bookmark manager →
          </Link>
        </div>
      </section>
    </main>
  );
}
