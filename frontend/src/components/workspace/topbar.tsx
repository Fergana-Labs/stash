"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search } from "lucide-react";
import CommandPalette from "@/components/CommandPalette";
import { StashIcon } from "@/components/SkillIcons";

/** Full-width top bar: octopus logo + breadcrumb (left), ⌘K search (center),
 *  share action (right). Account actions live on the rail's bottom avatar. */
export default function Topbar() {
  const pathname = usePathname();
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const searchBarRef = useRef<HTMLDivElement>(null);
  const isSearchPage = pathname === "/search";

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k" && !isSearchPage) {
        e.preventDefault();
        setCmdkOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isSearchPage]);

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 bg-rail px-3">
      <div className="flex shrink-0 items-center">
        <Link href="/" aria-label="Stash" className="flex shrink-0 items-center gap-1.5 text-brand-500">
          <StashIcon className="text-[22px]" />
          <span className="text-[15px] font-semibold tracking-tight text-foreground">Stash</span>
        </Link>
      </div>
      <div className="flex min-w-0 flex-1 justify-center">
        <div ref={searchBarRef} className="w-full max-w-2xl">
          <button
            onClick={() => setCmdkOpen(true)}
            className="flex h-9 w-full items-center gap-2.5 rounded-full border border-border bg-surface px-4 text-left text-[13px] text-muted-foreground shadow-sm transition-colors hover:border-brand-300 hover:bg-raised hover:text-foreground"
          >
            <Search className="h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">Search</span>
            <span className="rounded bg-base px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground ring-1 ring-border">⌘K</span>
          </button>
        </div>
      </div>
      <div className="w-[120px] shrink-0" />
      <CommandPalette open={cmdkOpen} onClose={() => setCmdkOpen(false)} anchorRef={searchBarRef} searchScope={null} />
    </header>
  );
}
