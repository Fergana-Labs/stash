"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { Code, PageHeading, SectionHeading } from "@/components/developer/DocsPrimitives";
import WikiToggle from "@/components/developer/WikiToggle";
import WikiGraph from "@/components/memory/WikiGraph";
import {
  getUser,
  getUserWikiGraph,
  type EndUserFile,
  type EndUserSession,
  type EndUserSource,
  type EndUserWikiPage,
  type WikiGraph as WikiGraphData,
} from "@/lib/api";
import type { EndUser } from "@/lib/types";

export default function UserDetailRoute() {
  return (
    <DeveloperGate>
      <UserDetail />
    </DeveloperGate>
  );
}

function UserDetail() {
  const userId = String(useParams().userId);
  const [user, setUser] = useState<EndUser | null>(null);
  const [sessions, setSessions] = useState<EndUserSession[]>([]);
  const [files, setFiles] = useState<EndUserFile[]>([]);
  const [wikiPages, setWikiPages] = useState<EndUserWikiPage[]>([]);
  const [wikiGraph, setWikiGraph] = useState<WikiGraphData | null>(null);
  const [sources, setSources] = useState<EndUserSource[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setError(null);
    getUser(userId)
      .then((res) => {
        setUser(res.user);
        setSessions(res.sessions);
        setFiles(res.files);
        setWikiPages(res.notepad_pages);
        setSources(res.sources);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the user"));
    // The graph is decoration over the list — its failure shouldn't blank the page.
    getUserWikiGraph(userId)
      .then(setWikiGraph)
      .catch(() => setWikiGraph(null));
  }, [userId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error) {
    return <p className="text-[15px] text-error">Couldn&apos;t load the user: {error}</p>;
  }
  if (!user) {
    return <p className="text-[15px] text-muted-foreground">Loading…</p>;
  }

  return (
    <>
      <Link
        href="/developer/users"
        className="mb-6 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All users
      </Link>

      <PageHeading title={user.name}>
        <Code>{user.external_id}</Code> — the <Code>user_id</Code> your backend asserts on
        every call for this user.
      </PageHeading>

      <section className="mb-12">
        <SectionHeading>Shared memory</SectionHeading>
        <div className="mt-4 flex items-center gap-4 rounded border border-border bg-surface px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="text-[15px] text-foreground">
              {user.share_wiki
                ? "This user's sessions feed the shared wiki"
                : "This user is opted out of the shared wiki"}
            </div>
            <p className="mt-1 text-[13.5px] leading-6 text-muted-foreground">
              {user.share_wiki
                ? "The curator distils anonymized lessons from their sessions into the wiki every user's agent reads. Their identity never appears there."
                : "Their sessions stay in their own wiki. Anything already written to the shared wiki stays — an opt-out is not a retraction."}
            </p>
          </div>
          <WikiToggle user={user} onChanged={refresh} />
        </div>
      </section>

      <section className="mb-12">
        <div className="flex items-baseline justify-between gap-4">
          <SectionHeading>This user&apos;s wiki</SectionHeading>
          <Link
            href={`/folders/${user.notepad_folder_id}`}
            className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
          >
            Open folder
          </Link>
        </div>
        <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
          What the curator has learned about this user specifically — kept out of the shared
          wiki, in their own words and their own detail. Only this user&apos;s agent (and you)
          can read it.
        </p>
        {wikiPages.length === 0 ? (
          <Empty>
            Nothing yet. The curator writes here on its next run over this user&apos;s sessions.
          </Empty>
        ) : (
          <>
            {wikiGraph && wikiGraph.nodes.length > 0 && (
              <div className="mt-4 rounded border border-border bg-surface p-2">
                <WikiGraph data={wikiGraph} height={320} />
              </div>
            )}
            <div className="mt-4 overflow-hidden rounded border border-border bg-surface">
            {wikiPages.map((page) => (
              <Link
                key={page.id}
                href={`/p/${page.id}`}
                className="flex items-center gap-4 border-b border-border px-5 py-3.5 transition-colors last:border-b-0 hover:bg-raised"
              >
                <span className="min-w-0 flex-1 truncate text-[14.5px] text-foreground">
                  {page.name}
                </span>
                <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
                  {formatDate(page.updated_at)}
                </span>
              </Link>
            ))}
            </div>
          </>
        )}
      </section>

      <section className="mb-12">
        <SectionHeading>Sessions</SectionHeading>
        {sessions.length === 0 ? (
          <Empty>No sessions yet for this user.</Empty>
        ) : (
          <div className="mt-4 overflow-hidden rounded border border-border bg-surface">
            {sessions.map((s) => (
              <Link
                key={s.session_id}
                href={`/sessions/${encodeURIComponent(s.session_id)}`}
                className="flex items-center gap-4 border-b border-border px-5 py-3.5 transition-colors last:border-b-0 hover:bg-raised"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] text-foreground">
                    {s.title || s.session_id}
                  </span>
                  <span className="mt-0.5 block font-mono text-[12px] text-muted-foreground">
                    {s.agent_name || "agent"} · {s.event_count} event
                    {s.event_count === 1 ? "" : "s"}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
                  {formatDate(s.last_event_at)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section>
        <SectionHeading>Files</SectionHeading>
        <p className="mt-2 text-[13.5px] leading-6 text-muted-foreground">
          Everything this user&apos;s agent can read besides the wikis: files your backend
          uploaded with their <Code>user_id</Code>, and integrations connected for them
          alone. Your other users never see any of it.
        </p>
        {files.length === 0 ? (
          <Empty>
            No files yet. Files arrive when your backend uploads one with this user&apos;s{" "}
            <Code>user_id</Code>.
          </Empty>
        ) : (
          <div className="mt-4 overflow-hidden rounded border border-border bg-surface">
            {files.map((f) => (
              <Link
                key={f.id}
                href={`/f/${f.id}`}
                className="flex items-center gap-4 border-b border-border px-5 py-3.5 transition-colors last:border-b-0 hover:bg-raised"
              >
                <span className="min-w-0 flex-1 truncate text-[14.5px] text-foreground">
                  {f.name}
                </span>
                <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
                  {formatBytes(f.size_bytes)} · {formatDate(f.created_at)}
                </span>
              </Link>
            ))}
          </div>
        )}
        <div className="mt-6 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          Connected sources
        </div>
        {sources.length === 0 ? (
          <Empty>
            None connected. Add one with this user&apos;s <Code>user_id</Code> to scope it
            here.
          </Empty>
        ) : (
          <div className="mt-3 overflow-hidden rounded border border-border bg-surface">
            {sources.map((source) => (
              <Link
                key={source.id}
                href={`/integrations/${source.provider}?source=${source.id}`}
                className="flex items-center gap-4 border-b border-border px-5 py-3.5 transition-colors last:border-b-0 hover:bg-raised"
              >
                <span className="min-w-0 flex-1 truncate text-[14.5px] text-foreground">
                  {source.display_name}
                </span>
                <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
                  {source.type}
                  {source.last_synced_at ? ` · synced ${formatDate(source.last_synced_at)}` : ""}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-4 rounded border border-dashed border-border px-6 py-8 text-center text-[14px] leading-6 text-muted-foreground">
      {children}
    </p>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
