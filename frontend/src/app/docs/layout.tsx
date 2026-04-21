"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "../../hooks/useAuth";

interface NavSection {
  title: string;
  items: { href: string; label: string }[];
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
      { href: "/docs/cli", label: "CLI" },
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
  const { user } = useAuth();
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
    <div className="min-h-screen bg-base">
      <header className="sticky top-0 z-30 border-b border-border bg-base/95 backdrop-blur">
        <div className="h-14 max-w-[1440px] mx-auto px-6 lg:px-8 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/" className="text-lg font-bold font-display text-foreground tracking-tight">stash</Link>
            <span className="text-xs text-muted font-medium uppercase tracking-[0.2em]">Documentation</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/" className="text-xs text-dim hover:text-foreground">Dashboard</Link>
            {user ? (
              <span className="text-xs text-muted">{user.display_name || user.name}</span>
            ) : (
              <Link href="/login" className="text-xs text-brand hover:text-brand-hover">Sign in</Link>
            )}
          </div>
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
                        <Link
                          key={item.href}
                          href={item.href}
                          className={`block rounded-lg px-3 py-2 text-[13px] transition-colors ${
                            isActive
                              ? "bg-brand/8 text-brand font-medium"
                              : "text-dim hover:text-foreground hover:bg-raised"
                          }`}
                        >
                          {item.label}
                        </Link>
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
              className="rounded-[28px] border border-border bg-base px-6 py-8 sm:px-8 md:px-10"
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
                      className={`block text-[13px] leading-5 transition-colors hover:text-foreground ${
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
