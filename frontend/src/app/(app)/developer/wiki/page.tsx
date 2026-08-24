"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import DeveloperGate from "@/components/developer/DeveloperGate";
import WikiGraph from "@/components/memory/WikiGraph";
import {
  getDeveloperWikiGraph,
  getUserWikiGraph,
  listUsers,
  runCuratorNow,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import type { EndUser } from "@/lib/types";
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
  const [users, setUsers] = useState<EndUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshGraph = useCallback(() => {
    getDeveloperWikiGraph()
      .then(setGraph)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the wiki graph"));
  }, []);

  useEffect(() => {
    refreshGraph();
    listUsers()
      .then((res) => {
        setFolderId(res.workspace.external_wiki_folder_id);
        setUsers(res.users);
      })
      .catch(() => setFolderId(null));
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [refreshGraph]);

  // The run happens on the worker; poll until pages start appearing.
  function pollWhileRunning() {
    if (pollTimer.current) clearInterval(pollTimer.current);
    pollTimer.current = setInterval(refreshGraph, 5000);
  }

  useEffect(() => {
    if (graph && graph.nodes.length > 0 && pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, [graph]);

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
          <EmptyGraph onStarted={pollWhileRunning} />
        )}
      </div>

      {users.length > 0 && (
        <div className="mt-10">
          <div className="sys-label mb-1.5">Per-user wikis</div>
          <p className="mb-3 text-[12.5px] leading-5 text-muted-foreground">
            What the curator knows about each user individually. Nothing here is shared:
            a user&apos;s agent reads the shared wiki above plus their own wiki, never
            anyone else&apos;s.
          </p>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {users.map((user) => (
              <UserWikiCard key={user.id} user={user} />
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

function EmptyGraph({ onStarted }: { onStarted: () => void }) {
  const [state, setState] = useState<"idle" | "starting" | "running">("idle");
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setState("starting");
    setError(null);
    try {
      await runCuratorNow();
      setState("running");
      onStarted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run");
      setState("idle");
    }
  }

  return (
    <div className="flex h-[560px] flex-col items-center justify-center gap-4 px-2 text-center">
      <p className="max-w-[52ch] text-[12.5px] leading-5 text-muted-foreground">
        No wiki pages yet. The curator compiles what your users have learned into a set of
        linked pages every night.
      </p>
      {state === "running" ? (
        <p className="text-[12.5px] text-muted-foreground">
          Running — pages appear here as the curator writes them.
        </p>
      ) : (
        <button
          onClick={() => void start()}
          disabled={state === "starting"}
          className="rounded-sm bg-brand-500 px-3.5 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50"
        >
          {state === "starting" ? "Starting…" : "Run now"}
        </button>
      )}
      {error && <p className="text-[12.5px] text-error">{error}</p>}
    </div>
  );
}

/** Each user's wiki as a wiki: the same graph the user detail page shows,
 *  small enough to scan the whole customer base at once. */
function UserWikiCard({ user }: { user: EndUser }) {
  const [graph, setGraph] = useState<WikiGraphData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getUserWikiGraph(user.id)
      .then(setGraph)
      .catch(() => setFailed(true));
  }, [user.id]);

  return (
    <div className="overflow-hidden rounded border border-border bg-surface">
      <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
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
          href={`/folders/${user.wiki_folder_id}`}
          className="shrink-0 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
        >
          Open wiki
        </Link>
      </div>
      {failed ? (
        <div className="flex h-[220px] items-center justify-center text-[12.5px] text-muted-foreground">
          Couldn&apos;t load this wiki.
        </div>
      ) : !graph ? (
        <div className="h-[220px] w-full animate-pulse bg-muted/40" />
      ) : graph.nodes.length > 0 ? (
        <WikiGraph data={graph} height={220} />
      ) : (
        <div className="flex h-[220px] items-center justify-center text-[12.5px] text-muted-foreground">
          Nothing curated for this user yet.
        </div>
      )}
    </div>
  );
}
