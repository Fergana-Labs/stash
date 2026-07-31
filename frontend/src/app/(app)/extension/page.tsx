"use client";

import { BookMarked, Bookmark, Globe, MessagesSquare } from "lucide-react";

// The one stable URL for getting the extension. Every CTA in the product
// links here, so when the Chrome Web Store listing goes live only this
// constant changes.
const CHROME_WEB_STORE_URL =
  "https://chromewebstore.google.com/detail/stash-sync/cggimcbkomkpielefiannhmenmoehbea";

const FEATURES = [
  {
    icon: Globe,
    title: "Clip any page",
    body: "Articles, PDFs, and every open tab. Saved clean and readable.",
  },
  {
    icon: BookMarked,
    title: "Bring your bookmarks",
    body: "Import the whole file. We fetch what's behind every link.",
  },
  {
    icon: Bookmark,
    title: "Twitter bookmarks",
    body: "Your X bookmarks, synced. Text, images, and threads kept.",
  },
  {
    icon: MessagesSquare,
    title: "AI chats",
    body: "ChatGPT and Claude, streamed in. Searchable like everything else.",
  },
];

const SHOTS = [
  {
    src: "/extension/save-page.jpg",
    caption: "Click the extension on any page and hit Save this tab — or Save all open tabs.",
  },
  {
    src: "/extension/saved-clip.jpg",
    caption: "The page lands in your Stash under Clips, kept in full and searchable.",
  },
];

export default function ExtensionPage() {
  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-12">
        <h1 className="font-display text-[30px] font-bold tracking-tight text-foreground">
          Save anything from the web
        </h1>
        <p className="mt-2 max-w-lg text-[14px] leading-relaxed text-dim">
          Automatic. Searchable. Read by your agents.
        </p>

        <div className="mt-7">
          <a
            href={CHROME_WEB_STORE_URL}
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-[13.5px] font-semibold text-white transition-colors hover:bg-brand-hover"
          >
            Add to Chrome — it&apos;s free
          </a>
        </div>

        <div className="mt-9 space-y-6">
          {SHOTS.map((s) => (
            <figure key={s.src}>
              <img
                src={s.src}
                alt={s.caption}
                className="w-full rounded-xl border border-border"
              />
              <figcaption className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
                {s.caption}
              </figcaption>
            </figure>
          ))}
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
          <div className="text-[13.5px] font-semibold text-foreground">One click to connect</div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">
            Click the icon and hit <span className="font-medium text-foreground">Connect</span>. You
            sign in once, in a normal tab. No tokens to copy. The extension gets its own key, and
            you can revoke it any time in Settings.
          </p>
        </div>
      </div>
    </div>
  );
}
