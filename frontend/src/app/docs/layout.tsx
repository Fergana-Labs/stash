"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
    ],
  },
  {
    title: "Guides",
    items: [
      { href: "/docs/consume", label: "Consume" },
      { href: "/docs/curate", label: "Curate" },
      { href: "/docs/collaborate", label: "Collaborate" },
      { href: "/docs/workspaces", label: "Workspaces" },
    ],
  },
  {
    title: "Reference",
    items: [
      { href: "/docs/cli", label: "CLI" },
      { href: "/docs/mcp", label: "MCP Server" },
      { href: "/docs/api", label: "REST API" },
      { href: "/docs/webhooks", label: "Webhooks" },
    ],
  },
];

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <div className="h-screen flex flex-col bg-base">
      <header className="h-14 flex items-center justify-between px-6 border-b border-border bg-surface flex-shrink-0">
        <div className="flex items-center gap-6">
          <Link href="/" className="text-lg font-bold font-display text-foreground tracking-tight">boozle</Link>
          <span className="text-xs text-muted font-medium uppercase tracking-wider">Documentation</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/" className="text-xs text-dim hover:text-foreground">Dashboard</Link>
          {user ? (
            <span className="text-xs text-muted">{user.display_name || user.name}</span>
          ) : (
            <Link href="/login" className="text-xs text-brand hover:text-brand-hover">Sign in</Link>
          )}
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-[220px] flex-shrink-0 border-r border-border overflow-y-auto py-4 bg-surface">
          {NAV.map((section) => (
            <div key={section.title} className="mb-4">
              <div className="px-4 py-1 text-[10px] font-semibold text-muted uppercase tracking-wider">
                {section.title}
              </div>
              {section.items.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`block px-4 py-1.5 text-[13px] transition-colors border-l-2 ${
                      isActive
                        ? "border-brand text-brand font-medium bg-brand/5"
                        : "border-transparent text-dim hover:text-foreground hover:border-border"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </aside>

        <main className="flex-1 overflow-y-auto">
          <div className="max-w-[720px] mx-auto px-8 py-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
