"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/rooms", label: "Workspaces", icon: "W" },
  { href: "/chats", label: "Chats", icon: "C" },
  { href: "/notebooks", label: "Notebooks", icon: "N" },
  { href: "/decks", label: "Decks", icon: "D" },
  { href: "/memory", label: "History", icon: "H" },
  { href: "/agents", label: "Agents", icon: "A" },
];

export default function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-[220px] flex-shrink-0 bg-surface border-r border-border flex flex-col">
      <div className="px-4 py-4">
        <Link href="/" className="text-lg font-bold font-display text-foreground tracking-tight">
          boozle
        </Link>
      </div>

      <nav className="flex-1 px-2 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive
                  ? "bg-brand/10 text-brand font-medium"
                  : "text-dim hover:text-foreground hover:bg-raised"
              }`}
            >
              <span
                className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold flex-shrink-0 ${
                  isActive
                    ? "bg-brand text-white"
                    : "bg-raised text-muted"
                }`}
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
