"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { SkeletonBlock } from "@/components/SkeletonStates";
import WikiFileTree, {
  wikiFolderCount,
  wikiPageCount,
} from "@/components/memory/WikiFileTree";
import { getMemoryTree } from "@/lib/api";
import type { Tree } from "@/lib/types";

/** The whole Memory wiki laid out as a file system — every folder and page,
 *  browsable in place. The graph on /memory shows how pages connect; this
 *  page shows where they live. */
export default function MemoryWikiRoute() {
  const [tree, setTree] = useState<Tree | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getMemoryTree()
      .then((t) => {
        if (!cancelled) setTree(t);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const pages = tree
    ? tree.pages.length + tree.folders.reduce((n, f) => n + wikiPageCount(f), 0)
    : 0;
  const folders = tree ? wikiFolderCount(tree.folders) : 0;
  const empty = !!tree && tree.folders.length === 0 && tree.pages.length === 0;

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-[860px] px-8 pb-10 pt-7">
        <Link
          href="/memory"
          className="inline-flex items-center gap-1 text-[12.5px] text-dim hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Your brain
        </Link>
        <h1 className="mt-2 font-display text-[22px] font-semibold tracking-tight text-foreground">
          Wiki file system
        </h1>
        <p className="mt-1 text-[13.5px] text-muted-foreground">
          {loading
            ? "Loading the Memory wiki…"
            : `${pages} ${pages === 1 ? "page" : "pages"} across ${folders} ${folders === 1 ? "folder" : "folders"} — the whole wiki, laid out as a file system. Click a page to open it.`}
        </p>

        <div className="mt-5">
          <div className="sys-label mb-1.5">Memory</div>
          <div className="card-soft p-3">
            {loading ? (
              <SkeletonBlock className="h-[320px] w-full" />
            ) : empty ? (
              <div className="flex h-[200px] items-center justify-center px-2 text-center text-[12.5px] text-muted-foreground">
                No wiki pages yet. Hit &quot;Curate wiki&quot; in the explorer and the
                agent will compile your history into linked pages.
              </div>
            ) : (
              tree && <WikiFileTree tree={tree} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
