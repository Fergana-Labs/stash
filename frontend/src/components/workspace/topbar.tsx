"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import CommandPalette from "@/components/CommandPalette";
import { StashIcon } from "@/components/SkillIcons";
import StashSwitcher from "./stash-switcher";

/** Full-width top bar: octopus logo + history nav (left), share action
 *  (right). Account actions live on the rail's bottom avatar. Search lives on
 *  the Files page, not here — ⌘K opens the palette everywhere except /files
 *  (where the page focuses its own search) and /search. */
export default function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const searchBarRef = useRef<HTMLDivElement>(null);
  const isSearchPage = pathname === "/search";
  const isFilesPage = pathname === "/files";

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k" && !isSearchPage && !isFilesPage) {
        e.preventDefault();
        setCmdkOpen((o) => !o);
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
        <StashSwitcher />
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
      {/* Empty center: the palette still anchors here when ⌘K summons it. */}
      <div className="flex min-w-0 flex-1 justify-center">
        <div ref={searchBarRef} className="w-full max-w-2xl" />
      </div>
      <div className="w-[120px] shrink-0" />
      <CommandPalette open={cmdkOpen} onClose={() => setCmdkOpen(false)} anchorRef={searchBarRef} searchScope={null} />
    </header>
  );
}

