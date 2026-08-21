"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import DeveloperGate from "@/components/developer/DeveloperGate";
import WikiGraph from "@/components/memory/WikiGraph";
import { getDeveloperWikiGraph, listTenants, type WikiGraph as WikiGraphData } from "@/lib/api";
import type { Tenant } from "@/lib/types";
import FolderDetailPage from "../../folders/[folderId]/FolderClient";

export default function DeveloperWiki() {
  return (
    <DeveloperGate>
      <SharedWiki />
    </DeveloperGate>
  );
}

/** The shared wiki twice over: the graph the curator maintains — every page it
 *  wrote and the references between them — above the folder itself, since the
 *  pages are ordinary (protected) files you still want to open and read. Below
 *  both, each user's own wiki, which lives outside this folder. */
function SharedWiki() {
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [users, setUsers] = useState<Tenant[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDeveloperWikiGraph()
      .then(setGraph)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the wiki graph"));
    listTenants()
      .then((res) => {
        setFolderId(res.workspace.external_wiki_folder_id);
        setUsers(res.tenants);
      })
      .catch(() => setFolderId(null));
  }, []);

  return (
    <div className="min-w-0">
      <div className="sys-label mb-1.5">Curated pages</div>
      <div className="card-soft p-3">
        {error ? (
          <div className="flex h-[560px] items-center justify-center px-2 text-center text-[12.5px] text-error">
            {error}
          </div>
        ) : !graph ? (
          <div className="h-[560px] w-full animate-pulse rounded bg-muted/40" />
        ) : graph.nodes.length > 0 ? (
          <WikiGraph data={graph} />
        ) : (
          <div className="flex h-[560px] items-center justify-center px-2 text-center text-[12.5px] text-muted-foreground">
            No wiki pages yet. The curator compiles what your users have learned into a set
            of linked pages every night — or run it now from Curator.
          </div>
        )}
      </div>
      <p className="mt-2 text-[12.5px] leading-5 text-muted-foreground">
        Every node is a page you can open — and edit: the curator treats your edits as
        source material and maintains around them. <span className="text-foreground">Wiki
        Index</span> and <span className="text-foreground">Log</span> are the curator&apos;s
        own bookkeeping: its catalog of every page, and its append-only changelog.
      </p>

      {users.length > 0 && (
        <div className="mt-10">
          <div className="sys-label mb-1.5">Per-user wikis</div>
          <p className="mb-3 text-[12.5px] leading-5 text-muted-foreground">
            What the curator knows about each user individually. Nothing here is shared:
            a user&apos;s agent reads the shared wiki above plus their own wiki, never
            anyone else&apos;s.
          </p>
          <div className="overflow-hidden rounded border border-border bg-surface">
            {users.map((user) => (
              <div
                key={user.id}
                className="flex items-center gap-4 border-b border-border px-5 py-3 last:border-b-0"
              >
                <Link
                  href={`/developer/users/${user.id}`}
                  className="min-w-0 flex-1 truncate text-[14px] text-foreground hover:text-brand-500"
                >
                  {user.name}
                </Link>
                <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
                  {user.external_id}
                </span>
                <Link
                  href={`/folders/${user.notepad_folder_id}`}
                  className="shrink-0 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
                >
                  Open wiki
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}

      {folderId && (
        <div className="mt-8">
          <FolderDetailPage folderId={folderId} />
        </div>
      )}
    </div>
  );
}
