"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

interface NavItem {
  href: string;
  label: string;
  children?: { href: string; label: string }[];
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const NAV: NavSection[] = [
  {
    title: "Getting Started",
    items: [
      { href: "/docs", label: "Overview" },
      { href: "/docs/quickstart", label: "Quickstart" },
      { href: "/docs/concepts", label: "Concepts" },
      { href: "/docs/self-hosting", label: "Self-Hosting" },
    ],
  },
  {
    title: "Reference",
    items: [
      {
        href: "/docs/cli",
        label: "CLI",
        children: [
          { href: "/docs/cli#install", label: "Install" },
          { href: "/docs/cli#first-time-setup", label: "First-time setup" },
          { href: "/docs/cli#authentication", label: "Authentication" },
          { href: "/docs/cli#notebooks", label: "Notebooks" },
          { href: "/docs/cli#history", label: "History" },
          { href: "/docs/cli#tables", label: "Tables" },
          { href: "/docs/cli#files", label: "Files" },
          { href: "/docs/cli#streaming-hooks", label: "Streaming & hooks" },
        ],
      },
    ],
  },
  {
    title: "Project",
    items: [
      { href: "/docs/contributing", label: "Contributing" },
    ],
  },
];

interface TocItem {
  id: string;
  label: string;
  level: number;
}

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [toc, setToc] = useState<TocItem[]>([]);

  useEffect(() => {
    const readToc = () => {
      const headings = Array.from(
        document.querySelectorAll<HTMLElement>("[data-docs-heading]")
      ).map((el) => ({
        id: el.id,
        label: el.dataset.docsLabel || el.innerText,
        level: Number(el.dataset.docsLevel || "2"),
      })).filter((item) => item.id && item.label);

      setToc(headings);
    };

    readToc();
    const timeout = window.setTimeout(readToc, 50);
    return () => window.clearTimeout(timeout);
  }, [pathname, children]);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border-subtle bg-background/95 backdrop-blur">
        <div className="h-16 max-w-[1440px] mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="font-display text-[22px] font-bold tracking-tight text-brand">
              stash
            </Link>
            <span className="text-[11px] text-muted font-mono uppercase tracking-[0.14em]">
              Documentation
            </span>
          </div>
          <nav className="flex items-center gap-8 text-[14px] text-dim">
            <Link href="https://github.com/Fergana-Labs/stash" className="hover:text-ink">
              GitHub
            </Link>
            <Link href="/" className="hover:text-ink">
              Home
            </Link>
          </nav>
        </div>
      </header>

      <div className="max-w-[1440px] mx-auto px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_220px] gap-8 lg:gap-10">
          <aside className="hidden lg:block">
            <div className="sticky top-24 rounded-2xl border border-border bg-surface p-4">
              {NAV.map((section) => (
                <div key={section.title} className="mb-5 last:mb-0">
                  <div className="px-2 pb-2 text-[10px] font-semibold text-muted uppercase tracking-[0.2em]">
                    {section.title}
                  </div>
                  <div className="space-y-1">
                    {section.items.map((item) => {
                      const isActive = pathname === item.href;
                      return (
                        <div key={item.href}>
                          <Link
                            href={item.href}
                            className={`block rounded-lg px-3 py-2 text-[13px] transition-colors ${
                              isActive
                                ? "bg-brand/10 text-brand font-medium"
                                : "text-dim hover:text-ink hover:bg-raised"
                            }`}
                          >
                            {item.label}
                          </Link>
                          {isActive && item.children && (
                            <div className="ml-3 mt-1 space-y-0.5 border-l border-border pl-3">
                              {item.children.map((child) => (
                                <a
                                  key={child.href}
                                  href={child.href}
                                  className="block rounded-md px-2 py-1.5 text-[12px] text-muted hover:text-ink hover:bg-raised transition-colors"
                                >
                                  {child.label}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </aside>

          <main className="min-w-0">
            <article
              data-docs-content
              className="rounded-[28px] border border-border bg-background px-6 py-8 sm:px-8 md:px-10"
            >
              {children}
            </article>
          </main>

          <aside className="hidden xl:block">
            <div className="sticky top-24 rounded-2xl border border-border bg-surface p-4">
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">
                On this page
              </div>
              {toc.length > 0 ? (
                <div className="mt-3 space-y-1">
                  {toc.map((item) => (
                    <a
                      key={item.id}
                      href={`#${item.id}`}
                      className={`block text-[13px] leading-5 transition-colors hover:text-ink ${
                        item.level > 2 ? "pl-3 text-muted" : "text-dim"
                      }`}
                    >
                      {item.label}
                    </a>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-xs text-muted">Article summary and headings will appear here.</p>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
