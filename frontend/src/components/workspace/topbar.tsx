"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Search } from "lucide-react";
import CommandPalette from "@/components/CommandPalette";
import { StashIcon } from "@/components/SkillIcons";
import { useFilesSearch } from "@/components/content/flat-files/search-store";
import ScopeSwitcher from "./scope-switcher";

/** Full-width top bar: octopus logo + breadcrumb (left), ⌘K search (center),
 *  share action (right). Account actions live on the rail's bottom avatar.
 *  On /files the search bar IS the page's search: it filters the flat list
 *  live instead of opening the palette. */
export default function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const searchBarRef = useRef<HTMLDivElement>(null);
  const filesInputRef = useRef<HTMLInputElement>(null);
  const isSearchPage = pathname === "/search";
  const isFilesPage = pathname === "/files";
  const filesQuery = useFilesSearch((s) => s.query);
  const setFilesQuery = useFilesSearch((s) => s.setQuery);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k" && !isSearchPage) {
        e.preventDefault();
        if (isFilesPage) filesInputRef.current?.focus();
        else setCmdkOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isSearchPage, isFilesPage]);

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 bg-rail px-3">
      <div className="flex shrink-0 items-center gap-2.5">
        <Link href="/" aria-label="Stash" className="flex shrink-0 items-center gap-1.5 text-brand-500">
          <StashIcon className="text-[22px]" />
          <span className="text-[15px] font-semibold tracking-tight text-foreground">Stash</span>
        </Link>
        <ScopeSwitcher />
        {/* IDE-style history nav: back is "wherever I just was", not "up a
            level" — the same arrows VS Code keeps beside its command center. */}
        <div className="flex items-center">
          <button
            type="button"
            onClick={() => router.back()}
            aria-label="Go back"
            title="Go back"
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-raised hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => router.forward()}
            aria-label="Go forward"
            title="Go forward"
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-raised hover:text-foreground"
          >
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="flex min-w-0 flex-1 justify-center">
        <div ref={searchBarRef} className="w-full max-w-2xl">
          {isFilesPage ? (
            <div className="flex h-9 w-full items-center gap-2.5 rounded-full border border-border bg-surface px-4 text-[13px] shadow-sm transition-colors focus-within:border-brand-300">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <input
                ref={filesInputRef}
                autoFocus
                value={filesQuery}
                onChange={(e) => setFilesQuery(e.target.value)}
                placeholder="Search everything in your stash…"
                className="min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground"
              />
              <span className="rounded bg-base px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground ring-1 ring-border">⌘K</span>
            </div>
          ) : (
            <button
              onClick={() => setCmdkOpen(true)}
              className="flex h-9 w-full items-center gap-2.5 rounded-full border border-border bg-surface px-4 text-left text-[13px] text-muted-foreground shadow-sm transition-colors hover:border-brand-300 hover:bg-raised hover:text-foreground"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="min-w-0 flex-1 truncate">Search</span>
              <span className="rounded bg-base px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground ring-1 ring-border">⌘K</span>
            </button>
          )}
        </div>
      </div>
      <div className="w-[120px] shrink-0" />
      <CommandPalette open={cmdkOpen} onClose={() => setCmdkOpen(false)} anchorRef={searchBarRef} searchScope={null} />
    </header>
  );
}
