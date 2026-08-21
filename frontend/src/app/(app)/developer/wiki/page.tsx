"use client";

import { useEffect, useState } from "react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import WikiGraph from "@/components/memory/WikiGraph";
import { getDeveloperWikiGraph, listTenants, type WikiGraph as WikiGraphData } from "@/lib/api";
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
 *  pages are ordinary (protected) files you still want to open and read. */
function SharedWiki() {
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDeveloperWikiGraph()
      .then(setGraph)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the wiki graph"));
    listTenants()
      .then((res) => setFolderId(res.workspace.external_wiki_folder_id))
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
            No wiki pages yet. The curator compiles what your tenants have learned into a set
            of linked pages every night — or run it now from Curator.
          </div>
        )}
      </div>

      {folderId && (
        <div className="mt-8">
          <FolderDetailPage folderId={folderId} />
        </div>
      )}
    </div>
  );
}
