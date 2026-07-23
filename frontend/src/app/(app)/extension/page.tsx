"use client";

import { BookMarked, Camera, Globe, MessagesSquare } from "lucide-react";

// The one stable URL for getting the extension. Every CTA in the product
// links here, so when the Chrome Web Store listing goes live only this
// constant changes.
const CHROME_WEB_STORE_URL: string | null = null;

const FEATURES = [
  {
    icon: Globe,
    title: "Clip any page",
    body: "Save the page you're reading — or every open tab — as a clean, readable copy in your Stash. PDFs included.",
  },
  {
    icon: BookMarked,
    title: "Import your bookmarks",
    body: "Bring your whole bookmarks file. Stash fetches every page's content in the background and files them under Clips.",
  },
  {
    icon: Camera,
    title: "Instagram saves",
    body: "Your saved posts sync automatically — captions, images, and video archived so they outlive the post.",
  },
  {
    icon: MessagesSquare,
    title: "AI chats",
    body: "ChatGPT and Claude conversations stream into your Stash as transcripts, searchable like everything else.",
  },
];

export default function ExtensionPage() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-12">
        <h1 className="font-display text-[30px] font-bold tracking-tight text-foreground">
          The Stash browser extension
        </h1>
        <p className="mt-2 max-w-lg text-[14px] leading-relaxed text-dim">
          Everything you read, save, and discuss — captured into your Stash while you browse.
        </p>

        <div className="mt-7">
          {CHROME_WEB_STORE_URL ? (
            <a
              href={CHROME_WEB_STORE_URL}
              target="_blank"
              rel="noopener"
              className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-[13.5px] font-semibold text-white transition-colors hover:bg-brand-hover"
            >
              Add to Chrome — it&apos;s free
            </a>
          ) : (
            <div className="rounded-lg border border-border bg-surface px-4 py-3 text-[13px] text-muted-foreground">
              The extension is in Chrome Web Store review — the install button lands here the
              moment it&apos;s approved.
            </div>
          )}
        </div>

        <div className="mt-9 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border border-border bg-base p-4">
              <f.icon className="h-4.5 w-4.5 text-brand" />
              <div className="mt-2.5 text-[14px] font-semibold text-foreground">{f.title}</div>
              <div className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">{f.body}</div>
            </div>
          ))}
        </div>

        <div className="mt-9 rounded-xl border border-border bg-base p-5">
          <div className="text-[13.5px] font-semibold text-foreground">How it connects</div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">
            After installing, click the extension icon and hit <span className="font-medium text-foreground">Connect</span>.
            You&apos;ll sign in to Stash once in a normal tab — no tokens to copy. The extension
            gets its own key you can revoke any time from Settings.
          </p>
        </div>
      </div>
    </div>
  );
}
