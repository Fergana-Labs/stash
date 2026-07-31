import type { Metadata } from "next";
import Link from "next/link";

import CtaPair from "../_components/CtaPair";
import SiteHeader from "../_components/SiteHeader";
import Texture from "../_components/Texture";

export const metadata: Metadata = {
  title: "Drive & bookmarks · Stash",
  description:
    "An AI-native Google Drive and bookmark manager. Everything you save — files, clipped pages, bookmarks, X saves, and AI chats — in one Drive your AI can actually read.",
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
  [
    "Your existing accounts",
    "Connect Gmail, Google Drive, Notion, and the rest. Stash reads them in place — nothing to migrate, nothing to re-file.",
  ],
  [
    "Files and folders",
    "Upload anything. Markdown, HTML, CSV, PDF, images — stored as real files in real folders, not rows in someone's database.",
  ],
];

const DRIVE = [
  [
    "Ask, don't dig",
    "Search by meaning, not filename. Ask what you saved about a topic six months ago and get the answer with links back to the source.",
  ],
  [
    "Your AI can read it",
    "The whole Drive mounts as a filesystem your agent can ls, find, and rg — through the CLI, the MCP server, or the API. Point ChatGPT or Claude at it and it works from what you actually saved.",
  ],
  [
    "It organizes itself",
    "Saved pages get titles, summaries, and tags on the way in. The pile stays browsable without you filing anything.",
  ],
  [
    "Share a link",
    "Any file or folder gets a public URL when you want one, and stays private when you don't.",
  ],
];

export default function PersonalPage() {
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
          <p className="kicker rise-in mb-6">For.users</p>
          <h1 className="max-w-[920px] text-balance font-display text-[clamp(40px,5.4vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-ink">
            An AI-native Google Drive{" "}
            <span className="text-brand">and bookmark manager.</span>
          </h1>
          <p className="mt-7 max-w-[620px] text-[18px] leading-[1.55] text-foreground">
            You save things all day — tabs, bookmarks, files, chats — into five
            different places you never look at again. Stash is one Drive for all
            of it, and unlike a folder of links, your AI can read every word of
            what&apos;s in it.
          </p>
          <div className="mt-9">
            <CtaPair />
          </div>
        </div>
      </section>

      <section className="border-b border-border-subtle bg-surface py-20 md:py-28">
        <div className="mx-auto max-w-[1200px] px-7">
          <p className="kicker">Everything.you.save</p>
          <h2 className="mt-5 max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            Saving to it takes one click. Usually zero.
          </h2>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
          <p className="kicker">Your.drive</p>
          <h2 className="mt-5 max-w-[760px] text-balance font-display text-[clamp(28px,3.4vw,44px)] font-bold leading-[1.1] tracking-[-0.02em] text-ink">
            A bookmark manager that read the bookmarks.
          </h2>
          <p className="mt-5 max-w-[640px] text-[16px] leading-[1.6] text-foreground">
            A saved link is a link. Stash keeps the page — the whole text, the
            images, the PDF — so months later you can ask what it said instead
            of hoping the site is still up.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2">
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
            Stop saving things you&apos;ll never find again.
          </h2>
          <div className="mt-8 flex justify-center">
            <CtaPair align="center" />
          </div>
          <Link
            href="/company-brain"
            className="mt-6 inline-flex font-mono text-[13px] text-dim transition hover:text-brand"
          >
            Using it with a team? See Company Brain →
          </Link>
        </div>
      </section>
    </main>
  );
}
