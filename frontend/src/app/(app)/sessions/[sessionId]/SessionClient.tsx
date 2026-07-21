"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { useShareAction } from "@/components/ShellChromeContext";
import DownloadMenu from "@/components/DownloadMenu";
import ResourceShareButton from "@/components/share/ResourceShareButton";
import { SessionDetailSkeleton } from "@/components/SkeletonStates";
import { useAuth } from "@/hooks/useAuth";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import {
  fetchAuthed,
  getSessionDetail,
  getSessionEventsPage,
  listSkills,
  materializeSession,
  renameSession,
  trashItem,
  type SessionDetail,
  type SessionEvent,
  type Skill,
} from "@/lib/api";
import { routes } from "@/lib/workspace-routes";
import EditableTitle from "@/components/content/EditableTitle";

// One transcript page. The viewer loads this many turns at a time and fetches
// more on scroll, so long sessions don't load every event up front.
const TRANSCRIPT_PAGE_SIZE = 100;

interface MessageTurn {
  kind: "message";
  id: string;
  who: "user" | "assistant";
  name: string;
  time?: string;
  dateKey?: string;
  dateLabel?: string;
  content: string;
  toolName?: string | null;
}

function formatDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatSessionDate(date: Date): string {
  return date.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function cleanSessionTitle(title: string): string {
  return title
    .replace(/^\s*title:\s*/i, "")
    .replace(/^\s{0,3}#{1,6}\s*/, "")
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .replace(/`/g, "")
    .trim();
}

function sessionHeading(detail: SessionDetail | null, sessionId: string): string {
  const raw = (detail?.title || sessionId).trim();
  return cleanSessionTitle(raw) || sessionId.replace(/^acme-/, "");
}

function eventToTurn(ev: SessionEvent): MessageTurn {
  const createdAt = ev.created_at ? new Date(ev.created_at) : null;

  return {
    kind: "message",
    id: ev.id,
    who: ev.role,
    name: ev.role === "assistant" ? "agent" : "user",
    time: createdAt
      ? createdAt.toLocaleTimeString(undefined, {
          hour: "numeric",
          minute: "2-digit",
        })
      : undefined,
    dateKey: createdAt ? formatDateKey(createdAt) : undefined,
    dateLabel: createdAt ? formatSessionDate(createdAt) : undefined,
    content: ev.content,
    toolName: ev.tool_name,
  };
}

const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-orange-200", fg: "text-orange-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-teal-200", fg: "text-teal-800" },
];

function avatarFor(name: string) {
  // Deterministic color per author (no hardcoded names). djb2-ish hash.
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export default function SessionViewerPage({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const confirm = useConfirm();

  const [agentName, setAgentName] = useState("");
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [turns, setTurns] = useState<MessageTurn[]>([]);
  const [totalTurns, setTotalTurns] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  useBreadcrumbs(
    [
      { label: "Sessions" },
      { label: sessionDetail ? sessionHeading(sessionDetail, sessionId) : `#${sessionId}` },
    ],
    `session/${sessionId}`
  );

  const shareAction = useMemo(() => {
    if (!sessionDetail || !user) return null;
    return (
      <ResourceShareButton
        objectType="session"
        objectId={sessionDetail.id}
        resourceName={sessionHeading(sessionDetail, sessionId)}
        resourceUrlPath={routes.session(sessionId)}
        currentUser={user}
      />
    );
  }, [sessionDetail, sessionId, user]);
  useShareAction(shareAction);

  const load = useCallback(async () => {
    try {
      const detail = await getSessionDetail(sessionId);
      const page = await getSessionEventsPage(sessionId, TRANSCRIPT_PAGE_SIZE, 0);
      setAgentName(
        detail.agent_name || page.events.find((event) => event.agent_name)?.agent_name || ""
      );
      setSessionDetail(detail);
      setTurns(page.events.map(eventToTurn));
      setTotalTurns(page.total);
      setHasMore(page.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load session");
    }
  }, [sessionId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const page = await getSessionEventsPage(sessionId, TRANSCRIPT_PAGE_SIZE, turns.length);
      setTurns((prev) => [...prev, ...page.events.map(eventToTurn)]);
      setHasMore(page.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load more messages");
    } finally {
      setLoadingMore(false);
    }
  }, [sessionId, loadingMore, hasMore, turns.length]);

  // Auto-load the next page when the sentinel scrolls into view; the button it
  // wraps is the manual fallback if the observer can't fire.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore();
      },
      { rootMargin: "600px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  if (loading) return <SessionDetailSkeleton />;
  if (!user) return null;
  if (!sessionDetail && turns.length === 0 && !error) return <SessionDetailSkeleton />;

  const sessionDate = turns.find((turn) => turn.dateLabel)?.dateLabel;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto grid max-w-[1100px] gap-7 px-12 pb-20 pt-7 lg:grid-cols-[minmax(0,1fr)_260px]">
        <main className="min-w-0">
          <div className="mb-2 flex items-start justify-between gap-4 border-b border-border pb-3.5">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                {agentName ? (
                  <span className="tag tag-agent">agent · {agentName}</span>
                ) : (
                  <span className="tag tag-agent">agent</span>
                )}
                <span className="sys-label">session</span>
                {sessionDetail?.linear_tickets.map((ticket) => (
                  <LinearTicketPill key={ticket.ticket_identifier} ticket={ticket} />
                ))}
              </div>
              <h1 className="mt-1.5 font-display text-[28px] font-bold leading-tight tracking-[-0.02em]">
                <EditableTitle
                  value={sessionHeading(sessionDetail, sessionId)}
                  onSave={async (next) => {
                    const { title } = await renameSession(sessionId, next);
                    setSessionDetail((prev) => (prev ? { ...prev, title } : prev));
                    return title;
                  }}
                />
              </h1>
              {totalTurns > 0 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-2.5 text-[12px] text-muted-foreground">
                  {sessionDate && <span>{sessionDate}</span>}
                  {sessionDate && <span>·</span>}
                  <span>
                    {totalTurns} message{totalTurns === 1 ? "" : "s"}
                  </span>
                </div>
              )}
            </div>
            <div className="flex flex-shrink-0 items-center gap-1.5">
              {sessionDetail && (
                <SaveToSkillButton
                  sessionId={sessionId}
                  onSaved={(pageId) => router.push(routes.page(pageId))}
                />
              )}
              {sessionId.startsWith("agent-") && (
                // Web chats (started in the Agents tab) can be resumed and
                // continued server-side from where they left off.
                <Link
                  href={`/agents?resume=${encodeURIComponent(sessionId)}`}
                  className="inline-flex items-center gap-1 rounded-md bg-[var(--color-brand-600)] px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-[var(--color-brand-700)]"
                >
                  Resume in chat →
                </Link>
              )}
              <DownloadMenu
                options={[
                  {
                    label: "Download transcript (.jsonl)",
                    onSelect: async () => {
                      const path = `/api/v1/me/transcripts/${encodeURIComponent(
                        sessionId
                      )}/export.jsonl`;
                      const res = await fetchAuthed(path);
                      if (!res.ok) return;
                      const blob = await res.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `session-${sessionId}.jsonl`;
                      document.body.appendChild(a);
                      a.click();
                      a.remove();
                      URL.revokeObjectURL(url);
                    },
                  },
                  ...(sessionDetail
                    ? [
                        {
                          label: "Delete",
                          destructive: true,
                          onSelect: async () => {
                            const ok = await confirm({
                              title: `Move session "${sessionId}" to trash?`,
                              confirmLabel: "Delete",
                            });
                            if (!ok) return;
                            try {
                              await trashItem("session", sessionDetail.id);
                              router.push("/sessions");
                            } catch (e) {
                              setError(
                                e instanceof Error ? e.message : "Delete failed"
                              );
                            }
                          },
                        },
                      ]
                    : []),
                ]}
              />
            </div>
          </div>

          {error && (
            <div className="mb-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          <div className="flex flex-col">
            {turns.map((turn, i) => {
              const previousTurn = turns[i - 1];
              const dateDividerLabel =
                turn.dateLabel && turn.dateKey !== previousTurn?.dateKey
                  ? turn.dateLabel
                  : null;

              return (
                <div key={i}>
                  {dateDividerLabel ? <DateDivider label={dateDividerLabel} /> : null}
                  <MessageRow turn={turn} index={i} />
                </div>
              );
            })}
            {hasMore && (
              <div ref={sentinelRef} className="flex justify-center py-4">
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="cursor-pointer rounded-md border border-border px-3 py-1.5 text-[12.5px] text-muted-foreground hover:text-foreground disabled:cursor-default disabled:opacity-60"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
            {!error && totalTurns === 0 && (
              <div className="rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted-foreground">
                No transcript events yet.
              </div>
            )}
          </div>
        </main>
        <SessionAside detail={sessionDetail} />
      </div>
    </div>
  );
}

// Compact inline picker: choose a skill folder, freeze the transcript into a
// markdown page inside it.
function SaveToSkillButton({
  sessionId,
  onSaved,
}: {
  sessionId: string;
  onSaved: (pageId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (!open || skills !== null) return;
    listSkills()
      .then(setSkills)
      .catch(() => setSkills([]));
  }, [open, skills]);

  async function save(skill: Skill) {
    setBusy(true);
    setMessage("");
    try {
      const page = await materializeSession(sessionId, skill.folder_id);
      setOpen(false);
      onSaved(page.id);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="cursor-pointer rounded-md border border-border bg-base px-2.5 py-1.5 text-[12.5px] font-medium text-foreground hover:bg-raised"
      >
        Save to Skill <span aria-hidden className="text-[10px]">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-56 overflow-hidden rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-lg">
          {skills === null && (
            <div className="px-3 py-1.5 text-muted-foreground">Loading…</div>
          )}
          {skills?.length === 0 && (
            <div className="px-3 py-1.5 text-muted-foreground">No skills yet.</div>
          )}
          {skills?.map((skill) => (
            <button
              key={skill.folder_id}
              type="button"
              disabled={busy}
              onClick={() => void save(skill)}
              className="block w-full cursor-pointer truncate px-3 py-1.5 text-left text-foreground hover:bg-raised disabled:opacity-50"
            >
              {skill.name}
            </button>
          ))}
          {message && <div className="px-3 py-1.5 text-red-500">{message}</div>}
        </div>
      )}
    </div>
  );
}

function SessionAside({ detail }: { detail: SessionDetail | null }) {
  const filesTouched = normalizeStringList(detail?.files_touched);
  const artifacts = detail?.artifacts ?? [];
  const tickets = detail?.linear_tickets ?? [];

  return (
    <aside className="hidden lg:block">
      <div className="sticky top-16 flex flex-col gap-3">
        {tickets.length > 0 && (
          <div className="card-soft p-3.5">
            <div className="sys-label">Linear</div>
            <div className="mt-2 flex flex-col gap-1.5">
              {tickets.map((ticket) => (
                <LinearTicketAsideRow key={ticket.ticket_identifier} ticket={ticket} />
              ))}
            </div>
          </div>
        )}

        <div className="card-soft p-3.5">
          <div className="sys-label">Artifacts</div>
          {filesTouched.length > 0 && (
            <div className="mt-2 flex flex-col gap-1.5">
              {filesTouched.map((file) => (
                <div
                  key={file}
                  className="flex items-center gap-1.5 rounded-md border border-border-subtle bg-base px-2 py-1.5 font-mono text-[11px] text-foreground"
                >
                  <FileGlyph />
                  <span className="truncate">{file}</span>
                </div>
              ))}
            </div>
          )}
          {artifacts.length > 0 && (
            <div className={"flex flex-col gap-1.5 " + (filesTouched.length > 0 ? "mt-2" : "mt-2")}>
              {artifacts.map((artifact) => (
                <a
                  key={artifact.id}
                  href={artifact.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="linkrow px-2 py-1.5 font-mono text-[11px]"
                >
                  <FileGlyph />
                  <span className="min-w-0 flex-1 truncate">{artifact.file_path}</span>
                  <span className="sys-label" style={{ fontSize: 10 }}>
                    {formatBytes(artifact.size_bytes)}
                  </span>
                </a>
              ))}
            </div>
          )}
          {filesTouched.length === 0 && artifacts.length === 0 && (
            <div className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
              No artifacts recorded.
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function LinearTicketAsideRow({
  ticket,
}: {
  ticket: NonNullable<SessionDetail["linear_tickets"][number]>;
}) {
  const metadata = ticketMetadata(ticket);
  const content = (
    <>
      <LinearTicketPill ticket={ticket} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium text-foreground">
          {ticket.ticket_title || ticket.ticket_identifier}
        </span>
        {metadata && (
          <span className="block truncate text-[11px] text-muted-foreground">
            {metadata}
          </span>
        )}
      </span>
    </>
  );

  if (!ticket.ticket_url) {
    return <div className="linkrow px-2 py-1.5">{content}</div>;
  }

  return (
    <a
      href={ticket.ticket_url}
      target="_blank"
      rel="noopener noreferrer"
      className="linkrow px-2 py-1.5"
    >
      {content}
    </a>
  );
}

function ticketMetadata(ticket: NonNullable<SessionDetail["linear_tickets"][number]>): string {
  return [
    ticket.ticket_status,
    ticket.ticket_assignee_name,
    ticket.ticket_project_name,
  ]
    .filter(Boolean)
    .join(" · ");
}

function LinearTicketPill({
  ticket,
}: {
  ticket: NonNullable<SessionDetail["linear_tickets"][number]>;
}) {
  return (
    <span
      className="inline-flex max-w-full shrink-0 items-center rounded border border-[var(--color-brand-200)] bg-[var(--color-brand-50)] px-2 py-0.5 font-mono text-[11px] font-semibold text-[var(--color-brand-700)]"
      title={ticket.ticket_title || ticket.ticket_identifier}
    >
      {ticket.ticket_identifier}
    </span>
  );
}

function FileGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="flex-shrink-0 text-muted-foreground">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function normalizeStringList(value: string[] | string | null | undefined): string[] {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  const parsed = JSON.parse(value);
  return Array.isArray(parsed) ? parsed.map(String) : [];
}

function DateDivider({ label }: { label: string }) {
  return (
    <div className="my-4 flex items-center gap-3 text-[11px] font-medium text-muted-foreground">
      <span className="h-px flex-1 bg-border" />
      <span>{label}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

function MessageRow({ turn, index }: { turn: MessageTurn; index: number }) {
  const isAgent = turn.who === "assistant";
  const avatar = avatarFor(turn.name);
  const rowId = turn.toolName ? `tool-call-${index}` : undefined;
  return (
    <div id={rowId} className="msg-row group scroll-mt-16 rounded-md px-2 py-2">
      <div className="flex gap-3">
        <span
          className={
            "inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-semibold " +
            avatar.bg +
            " " +
            avatar.fg
          }
        >
          {initials(turn.name)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 text-[12.5px]">
            <span className="font-semibold text-foreground">{turn.name}</span>
            {isAgent ? (
              <span className="tag tag-agent">agent</span>
            ) : (
              <span className="tag tag-human">human</span>
            )}
            {turn.toolName && (
              <span className="rounded bg-surface px-1.5 py-0 font-mono text-[10.5px] text-dim ring-1 ring-border">
                {turn.toolName}
              </span>
            )}
            <span className="flex-1" />
            {turn.time && (
              <span className="sys-label" style={{ fontSize: 10 }}>
                {turn.time}
              </span>
            )}
          </div>
          {turn.toolName ? (
            <div className="mt-1 whitespace-pre-wrap rounded-md border border-border-subtle bg-surface px-2.5 py-2 font-mono text-[12px] leading-relaxed text-foreground">
              {turn.content}
            </div>
          ) : (
            <div className="markdown-content mt-1 text-[13.5px] leading-relaxed text-foreground">
              <Markdown remarkPlugins={[remarkGfm]}>{turn.content}</Markdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
