"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
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
  getSessionEvents,
  getSessionEventsPage,
  listFiles,
  listSkills,
  materializeSession,
  renameSession,
  trashItem,
  type FolderBackedSkill,
  type SessionDetail,
} from "@/lib/api";
import type { FileInfo } from "@/lib/types";
import EditableTitle from "@/components/content/EditableTitle";
import { getScope } from "@/lib/scope-store";
import { useTabTitle } from "@/lib/workspace-store";
import { eventToTurn, toolDisplay, type MessageTurn } from "./transcript";
import MinimapStrip from "./MinimapStrip";
import { MINIMAP_MIN_TURNS } from "./minimap";

// One transcript page. The viewer loads this many turns at a time and fetches
// more on scroll, so long sessions don't load every event up front.
const TRANSCRIPT_PAGE_SIZE = 100;

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

// A session is named by its title everywhere a person sees it, so the file
// they end up with on disk is named that way too.
function transcriptFilename(detail: SessionDetail, sessionId: string): string {
  const name = sessionHeading(detail, sessionId)
    .replace(/[/\\:*?"<>|]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  return `${name}.jsonl`;
}

export default function SessionViewerPage({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const { user, loading } = useAuth();
  const confirm = useConfirm();

  const [agentName, setAgentName] = useState("");
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  // The developer console has no sidebar entry for an open transcript, so it
  // needs a way back to the list. Resolved in an effect to match the
  // server-rendered markup (the scope lives in localStorage).
  const [inDeveloperConsole, setInDeveloperConsole] = useState(false);
  useEffect(() => {
    setInDeveloperConsole(getScope()?.view === "developer");
  }, []);
  useTabTitle("session", sessionId, sessionDetail && sessionHeading(sessionDetail, sessionId));
  const [turns, setTurns] = useState<MessageTurn[]>([]);
  const [totalTurns, setTotalTurns] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  useBreadcrumbs(
    [
      { label: "Sessions" },
      { label: sessionDetail ? sessionHeading(sessionDetail, sessionId) : "Session" },
    ],
    `session/${sessionId}`
  );

  // All session actions live in the workbench header row, next to Share —
  // the transcript itself stays chrome-free.
  const headerActions = useMemo(() => {
    if (!sessionDetail || !user) return null;
    return (
      <>
        <SaveToSkillButton
          sessionId={sessionId}
          onSaved={(pageId) => router.push(`/p/${pageId}`)}
        />
        <ResourceShareButton
          objectType="session"
          objectId={sessionDetail.id}
          resourceName={sessionHeading(sessionDetail, sessionId)}
          resourceUrlPath={`/sessions/${encodeURIComponent(sessionId)}`}
          currentUser={user}
        />
        <DownloadMenu
          options={[
            {
              label: "Download transcript (.jsonl)",
              onSelect: async () => {
                const path = `/api/v1/me/transcripts/export.jsonl?session_id=${encodeURIComponent(
                  sessionId
                )}`;
                const res = await fetchAuthed(path);
                if (!res.ok) return;
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = transcriptFilename(sessionDetail, sessionId);
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
              },
            },
            {
              label: "Delete",
              destructive: true,
              onSelect: async () => {
                const ok = await confirm({
                  title: `Move session "${sessionHeading(sessionDetail, sessionId)}" to trash?`,
                  confirmLabel: "Delete",
                });
                if (!ok) return;
                try {
                  await trashItem("session", sessionDetail.id);
                  router.push("/sessions");
                } catch (e) {
                  setError(e instanceof Error ? e.message : "Delete failed");
                }
              },
            },
          ]}
        />
      </>
    );
  }, [sessionDetail, sessionId, user, router, confirm]);
  useShareAction(headerActions);

  const load = useCallback(async () => {
    try {
      const detail = await getSessionDetail(sessionId);
      const page = await getSessionEventsPage(sessionId, TRANSCRIPT_PAGE_SIZE, 0);
      setAgentName(
        detail.agent_name || page.events.find((event) => event.agent_name)?.agent_name || ""
      );
      setSessionDetail(detail);
      setTurns(
        page.events.map((ev) => eventToTurn(ev, sessionId, detail.created_by_display_name))
      );
      setTotalTurns(page.total);
      setHasMore(page.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load session");
    }
  }, [sessionId]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  const humanName = sessionDetail?.created_by_display_name ?? null;

  // True while the full-transcript drain is in flight (see drainTranscript).
  const [loadingAll, setLoadingAll] = useState(false);

  const loadMore = useCallback(async () => {
    // A drain in flight will replace the whole list; appending a page on top
    // of it would duplicate turns.
    if (loadingMore || !hasMore || loadingAll) return;
    setLoadingMore(true);
    try {
      const page = await getSessionEventsPage(sessionId, TRANSCRIPT_PAGE_SIZE, turns.length);
      setTurns((prev) => [
        ...prev,
        ...page.events.map((ev) => eventToTurn(ev, sessionId, humanName)),
      ]);
      setHasMore(page.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load more messages");
    } finally {
      setLoadingMore(false);
    }
  }, [sessionId, loadingMore, hasMore, loadingAll, turns.length, humanName]);

  // --- In-session search + human-turn navigation -------------------------
  const [query, setQuery] = useState("");
  const [focusIndex, setFocusIndex] = useState<number | null>(null);

  // The one full-transcript drain, shared by search (matches must cover the
  // whole session) and the minimap (its blocks map the whole session).
  const drainTranscript = useCallback(() => {
    if (!hasMore || loadingAll) return;
    setLoadingAll(true);
    getSessionEvents(sessionId)
      .then((events) => {
        setTurns(events.map((ev) => eventToTurn(ev, sessionId, humanName)));
        setHasMore(false);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load transcript"))
      .finally(() => setLoadingAll(false));
  }, [hasMore, loadingAll, sessionId, humanName]);

  // Searching only what's paged in would silently miss the rest of a long
  // session, so the first keystroke drains the full transcript once.
  useEffect(() => {
    if (query.trim()) drainTranscript();
  }, [query, drainTranscript]);

  // The minimap only earns its gutter on a wide viewport and a session long
  // enough that scrolling blind hurts. Resolved via matchMedia (not a CSS
  // hidden class) so narrow viewports never pay for the full-transcript drain.
  const [wideViewport, setWideViewport] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setWideViewport(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  const showMinimap = wideViewport && totalTurns >= MINIMAP_MIN_TURNS;

  useEffect(() => {
    if (showMinimap) drainTranscript();
  }, [showMinimap, drainTranscript]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const hits: number[] = [];
    turns.forEach((turn, i) => {
      const haystack = `${turn.name} ${turn.toolName ?? ""} ${turn.content}`.toLowerCase();
      if (haystack.includes(q)) hits.push(i);
    });
    return hits;
  }, [turns, query]);

  const humanTurnIndices = useMemo(
    () => turns.flatMap((turn, i) => (turn.who === "user" ? [i] : [])),
    [turns]
  );

  const jumpTo = useCallback((index: number) => {
    setFocusIndex(index);
    document.getElementById(`turn-${index}`)?.scrollIntoView({ block: "center" });
  }, []);

  const jumpToMatch = useCallback(
    (direction: 1 | -1) => {
      if (matches.length === 0) return;
      const pos = matches.indexOf(focusIndex ?? -1);
      const nextPos =
        pos === -1
          ? direction === 1
            ? 0
            : matches.length - 1
          : (pos + direction + matches.length) % matches.length;
      jumpTo(matches[nextPos]);
    },
    [matches, focusIndex, jumpTo]
  );

  const jumpToHuman = useCallback(
    (direction: 1 | -1) => {
      const from = focusIndex ?? (direction === 1 ? -1 : turns.length);
      const next =
        direction === 1
          ? humanTurnIndices.find((i) => i > from)
          : [...humanTurnIndices].reverse().find((i) => i < from);
      if (next !== undefined) jumpTo(next);
    },
    [focusIndex, turns.length, humanTurnIndices, jumpTo]
  );

  // Auto-load the next page when the sentinel scrolls into view; the button it
  // wraps is the manual fallback if the observer can't fire.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  // The transcript's scroll container; the minimap reads it to place its lens.
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
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
    <div className="flex min-h-0 flex-1">
      <div ref={scrollContainerRef} className="scroll-thin min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-[1100px] gap-7 px-12 pb-20 pt-7 lg:grid-cols-[minmax(0,1fr)_260px]">
          <main className="min-w-0">
            {inDeveloperConsole && (
              <Link
                href="/developer/sessions"
                className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                All sessions
              </Link>
            )}
            <div className="mb-2 border-b border-border pb-3.5">
              <h1 className="font-display text-[28px] font-bold leading-tight tracking-[-0.02em]">
                <EditableTitle
                  value={sessionHeading(sessionDetail, sessionId)}
                  onSave={async (next) => {
                    const { title } = await renameSession(sessionId, next);
                    setSessionDetail((prev) => (prev ? { ...prev, title } : prev));
                    return title;
                  }}
                />
              </h1>
              {(sessionDate || totalTurns > 0 || agentName || sessionDetail?.cwd) && (
                <div className="mt-1.5 flex flex-wrap items-center gap-2.5 text-[12px] text-muted-foreground">
                  {sessionDate && <span>{sessionDate}</span>}
                  {totalTurns > 0 && (
                    <span>
                      {totalTurns} message{totalTurns === 1 ? "" : "s"}
                    </span>
                  )}
                  {agentName && <span title="Agent that ran this session">{agentName}</span>}
                  {sessionDetail?.cwd && (
                    <span className="font-mono text-[11px]" title="Working directory">
                      {sessionDetail.cwd}
                    </span>
                  )}
                </div>
              )}
            </div>

            {totalTurns > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") jumpToMatch(e.shiftKey ? -1 : 1);
                  }}
                  placeholder="Search this session…"
                  className="w-56 rounded-md border border-border bg-base px-2.5 py-1.5 text-[12.5px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-600)]"
                />
                {query.trim() && (
                  <>
                    <span className="text-[12px] text-muted-foreground">
                      {loadingAll
                        ? "Loading full transcript…"
                        : `${matches.length} match${matches.length === 1 ? "" : "es"}`}
                    </span>
                    <JumpButton label="Previous match" onClick={() => jumpToMatch(-1)} disabled={matches.length === 0}>
                      ↑
                    </JumpButton>
                    <JumpButton label="Next match" onClick={() => jumpToMatch(1)} disabled={matches.length === 0}>
                      ↓
                    </JumpButton>
                  </>
                )}
                {humanTurnIndices.length > 0 && (
                  <>
                    <span className="flex-1" />
                    <JumpButton label="Previous human message" onClick={() => jumpToHuman(-1)}>
                      ↑ human
                    </JumpButton>
                    <JumpButton label="Next human message" onClick={() => jumpToHuman(1)}>
                      ↓ human
                    </JumpButton>
                  </>
                )}
              </div>
            )}

            {error && (
              <div className="mb-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
                {error}
              </div>
            )}

            <div className="flex flex-col">
              {turns.map((turn, i) => {
                // The header already names the session's date, so the first
                // message needs no divider — only an actual date change does.
                const previousTurn = turns[i - 1];
                const dateDividerLabel =
                  i > 0 && turn.dateLabel && turn.dateKey !== previousTurn?.dateKey
                    ? turn.dateLabel
                    : null;

                return (
                  <div key={i}>
                    {dateDividerLabel ? <DateDivider label={dateDividerLabel} /> : null}
                    <MessageRow turn={turn} index={i} focused={focusIndex === i} />
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
              {!hasMore && turns.length > 0 && (
                <DateDivider
                  label={`End of session · ${totalTurns} message${totalTurns === 1 ? "" : "s"}`}
                />
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
      {showMinimap && (
        <MinimapStrip
          turns={turns}
          loaded={!hasMore}
          scrollRef={scrollContainerRef}
          matches={matches}
          onJump={jumpTo}
        />
      )}
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
  const [skills, setSkills] = useState<FolderBackedSkill[] | null>(null);
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
      // Saving a session writes a page into the skill's folder, which a
      // source-backed skill has not got — its content lives in its source.
      .then((all) => setSkills(all.filter((s) => s.backing === "folder")))
      .catch(() => setSkills([]));
  }, [open, skills]);

  async function save(skill: FolderBackedSkill) {
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
        title="Save this session's transcript as a page inside a skill you pick"
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

  // Paths the session touched are only local paths; a path becomes a link
  // when a file with that name exists in the viewer's stash.
  const [stashFiles, setStashFiles] = useState<FileInfo[]>([]);
  useEffect(() => {
    if (filesTouched.length === 0) return;
    listFiles()
      .then(setStashFiles)
      .catch(() => setStashFiles([]));
  }, [filesTouched.length]);

  const stashFileFor = (path: string): FileInfo | undefined => {
    const basename = path.split("/").pop();
    return stashFiles.find((f) => f.name === basename);
  };

  return (
    <aside className="hidden lg:block">
      <div className="sticky top-16 flex flex-col gap-3">
        <div className="card-soft p-3.5">
          <div className="sys-label">Files referenced in this session</div>
          {filesTouched.length > 0 && (
            <div className="mt-2 flex flex-col gap-1.5">
              {filesTouched.map((file) => {
                const stashFile = stashFileFor(file);
                if (!stashFile) {
                  return (
                    <div
                      key={file}
                      className="flex items-center gap-1.5 rounded-md border border-border-subtle bg-base px-2 py-1.5 font-mono text-[11px] text-foreground"
                    >
                      <FileGlyph />
                      <span className="truncate">{file}</span>
                    </div>
                  );
                }
                return (
                  <Link
                    key={file}
                    href={`/f/${stashFile.id}`}
                    title={file}
                    className="linkrow px-2 py-1.5 font-mono text-[11px]"
                  >
                    <FileGlyph />
                    <span className="min-w-0 flex-1 truncate">{file}</span>
                  </Link>
                );
              })}
            </div>
          )}
          {artifacts.length > 0 && (
            <div className="mt-2 flex flex-col gap-1.5">
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
              No files recorded for this session.
            </div>
          )}
        </div>
      </div>
    </aside>
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

function JumpButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="cursor-pointer rounded-md border border-border px-2 py-1 text-[12px] text-muted-foreground hover:text-foreground disabled:cursor-default disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function MessageRow({
  turn,
  index,
  focused,
}: {
  turn: MessageTurn;
  index: number;
  focused: boolean;
}) {
  const isSystem = turn.who === "system";
  return (
    <div
      id={`turn-${index}`}
      className={
        "msg-row group scroll-mt-16 rounded-md px-2 py-2" +
        (focused ? " ring-2 ring-[var(--color-brand-300)]" : "")
      }
    >
      <div className="min-w-0">
        <div className="flex items-baseline gap-2 text-[12.5px]">
          <span
            className={
              "font-semibold " + (isSystem ? "text-muted-foreground" : "text-foreground")
            }
          >
            {turn.name}
          </span>
          {turn.who === "assistant" && <span className="tag tag-agent">agent</span>}
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
          <ToolTurn content={turn.content} />
        ) : (
          <div className="markdown-content mt-1 text-[13.5px] leading-relaxed text-foreground">
            <Markdown remarkPlugins={[remarkGfm]}>{turn.content}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
}

// Tool calls collapse to a one-line summary so a wall of tool use scrolls
// past in a few rows; the full input is one click away.
function ToolTurn({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  const { summary, body } = toolDisplay(content);
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-2.5 py-1.5 text-left font-mono text-[11.5px] text-muted-foreground hover:text-foreground"
      >
        <span aria-hidden className="text-[9px]">
          {open ? "▾" : "▸"}
        </span>
        <span className="min-w-0 flex-1 truncate">{summary}</span>
      </button>
      {open && (
        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-md border border-border-subtle bg-surface px-2.5 py-2 font-mono text-[12px] leading-relaxed text-foreground">
          {body}
        </pre>
      )}
    </div>
  );
}
