"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import MembersModal from "../../../components/MembersModal";
import StashQuickAdd from "../../../components/StashQuickAdd";
import HandoffPanel from "../../../components/stash/HandoffPanel";
import {
  FileIcon,
  FolderIcon,
  PageIcon,
  SessionsIcon,
  StashIcon,
  TableIcon,
  WikiIcon,
} from "../../../components/StashIcons";
import { useAuth } from "../../../hooks/useAuth";
import {
  createFolder,
  createPage,
  getStashOverview,
  getWorkspace,
  getWorkspaceMembers,
  joinWorkspace,
  listViews,
  updateWorkspace,
  uploadFile,
  type StashOverview,
  type StashView,
  type WikiFile,
} from "../../../lib/api";
import { useShareModal } from "../../../lib/shareModalContext";
import type { FileInfo, Folder, Workspace, WorkspaceMember } from "../../../lib/types";

interface CardItem {
  href: string;
  external?: boolean;
  icon: React.ReactNode;
  iconColor?: string;
  title: string;
  subtitle: string;
}

function CardGrid({ items, hover }: { items: CardItem[]; hover: "brand" | "indigo" }) {
  const hoverCls =
    hover === "indigo"
      ? "hover:border-indigo-300 hover:bg-indigo-50/30"
      : "hover:border-[var(--color-brand-200)] hover:bg-[var(--color-brand-50)]";
  return (
    <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
      {items.map((c) => {
        const cls =
          "flex items-center gap-3 rounded-lg border border-border bg-base p-3 text-left transition-colors " +
          hoverCls;
        const inner = (
          <>
            <span
              className={
                "flex h-7 w-7 items-center justify-center text-2xl " +
                (c.iconColor || "text-muted")
              }
            >
              {c.icon}
            </span>
            <div className="min-w-0">
              <div className="truncate text-[13.5px] font-semibold text-foreground">{c.title}</div>
              <div className="truncate text-[11.5px] text-muted">{c.subtitle}</div>
            </div>
          </>
        );
        return c.external ? (
          <a
            key={c.href + c.title}
            href={c.href}
            target="_blank"
            rel="noopener noreferrer"
            className={cls}
          >
            {inner}
          </a>
        ) : (
          <Link key={c.href + c.title} href={c.href} className={cls}>
            {inner}
          </Link>
        );
      })}
    </div>
  );
}

export default function StashHomePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const stashId = params.stashId as string;
  const { user, loading, logout } = useAuth();

  // Deep-link from the /v/[slug] creator-actions card: auto-open the members
  // modal when the URL says ?invite=open. Captured at mount so a later URL
  // change doesn't re-trigger.
  const initialInviteOpen = searchParams.get("invite") === "open";

  const [stash, setStash] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [spine, setSpine] = useState<StashOverview | null>(null);
  const [views, setViews] = useState<StashView[]>([]);
  const [error, setError] = useState("");
  const [membersOpen, setMembersOpen] = useState(initialInviteOpen);
  const shareModal = useShareModal();
  const shareVersion = shareModal.version;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const [stashResult, membersResult, spineResult, viewsResult] = await Promise.allSettled([
      getWorkspace(stashId),
      getWorkspaceMembers(stashId),
      getStashOverview(stashId),
      listViews(stashId),
    ]);

    if (stashResult.status === "fulfilled") {
      setStash(stashResult.value);
    } else {
      setError("Stash not found");
    }

    if (membersResult.status === "fulfilled") {
      setMembers(membersResult.value);
    }

    if (spineResult.status === "fulfilled") {
      setSpine(spineResult.value);
    }

    if (viewsResult.status === "fulfilled") {
      setViews(viewsResult.value);
    }
  }, [stashId]);

  const refreshSpine = useCallback(async () => {
    try {
      setSpine(await getStashOverview(stashId));
    } catch {
      /* private */
    }
  }, [stashId]);

  useEffect(() => {
    if (!user) return;
    load();
  }, [user, load, shareVersion]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const isMember = !!user && members.some((m) => m.user_id === user.id);

  async function handleJoin() {
    if (!stash) return;
    try {
      await joinWorkspace(stash.invite_code);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join");
    }
  }

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const sessions: CardItem[] = (spine?.sessions ?? []).slice(0, 6).map((s) => ({
    href: `/stashes/${stashId}/sessions/${encodeURIComponent(s.session_id)}`,
    icon: <SessionsIcon />,
    title: `#${s.session_id.length > 28 ? s.session_id.slice(0, 28) + "…" : s.session_id}`,
    subtitle: `${s.agent_name} · ${formatBytes(s.size_bytes)}`,
  }));

  // Root-level wiki contents only. Nested folders/pages/files surface
  // through their parent folder's detail page, not here.
  const rootFolders = (spine?.wiki?.folders ?? []).filter((f) => !f.parent_folder_id);
  const rootPages = (spine?.wiki?.pages ?? []).filter((p) => !p.folder_id);
  const rootFiles = (spine?.wiki?.files ?? []).filter((f) => !f.folder_id);

  const wikiFolderItems: CardItem[] = rootFolders.map((f) => ({
    href: `/stashes/${stashId}/folders/${f.id}`,
    icon: <FolderIcon />,
    title: f.name,
    subtitle: [
      f.page_count ? `${f.page_count} page${f.page_count === 1 ? "" : "s"}` : null,
      f.file_count ? `${f.file_count} file${f.file_count === 1 ? "" : "s"}` : null,
      f.has_skill ? "SKILL.md" : null,
    ]
      .filter(Boolean)
      .join(" · ") || "Empty folder",
  }));
  const wikiPageItems: CardItem[] = rootPages.map((p) => ({
    href: `/stashes/${stashId}/p/${p.id}`,
    icon: <PageIcon />,
    title: p.name.replace(/\.md$/, ""),
    subtitle: "Page",
  }));
  const wikiFileItems: CardItem[] = rootFiles.slice(0, 12).map((f) => {
    const isCsvLinked = f.content_type?.includes("csv") && f.linked_table_id;
    return {
      href: isCsvLinked
        ? `/tables/${f.linked_table_id}?workspaceId=${stashId}`
        : `/stashes/${stashId}/f/${f.id}`,
      icon: f.content_type?.includes("csv") ? <TableIcon /> : <FileIcon />,
      iconColor: f.content_type?.includes("csv")
        ? "text-emerald-600"
        : f.content_type?.includes("pdf")
        ? "text-rose-500"
        : f.content_type?.includes("html")
        ? "text-amber-600"
        : undefined,
      title: f.name,
      subtitle: isCsvLinked
        ? `table · ${formatBytes(f.size_bytes)}`
        : `${f.content_type || "file"} · ${formatBytes(f.size_bytes)}`,
    };
  });
  const wikiItems = [...wikiFolderItems, ...wikiPageItems, ...wikiFileItems];
  const totalFolders = spine?.wiki?.folders.length ?? 0;
  const totalPages = spine?.wiki?.pages.length ?? 0;
  const totalFiles = spine?.wiki?.files.length ?? 0;

  return (
    <>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div
          className="h-32 bg-gradient-to-r from-[var(--color-brand-200)] via-amber-100 to-rose-100 bg-cover bg-center"
          style={
            stash?.cover_image_url
              ? { backgroundImage: `url(${stash.cover_image_url})` }
              : stash?.color_gradient
              ? { backgroundImage: stash.color_gradient }
              : undefined
          }
        />
        <div className="mx-auto -mt-8 max-w-3xl px-12 pb-16">
          <div className="mb-2 flex h-12 w-12 items-center justify-center overflow-hidden text-5xl text-[var(--color-brand-700)]">
            {stash?.icon_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={stash.icon_url} alt="" className="h-12 w-12 rounded-lg object-cover" />
            ) : (
              <StashIcon />
            )}
          </div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
              {stash?.name || "Loading…"}
            </h1>
            {isMember && (
              <Link
                href={`/stashes/${stashId}/settings`}
                title="Stash settings"
                className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-foreground"
                aria-label="Settings"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </Link>
            )}
          </div>
          <StashDescription
            stash={stash}
            canEdit={isMember}
            onSaved={(updated) => setStash(updated)}
          />


          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <button
              onClick={() => setMembersOpen(true)}
              title="View, add, or remove members"
              className="rounded-md px-1.5 py-0.5 hover:bg-raised"
            >
              <MemberStack members={members} />
              <span className="ml-1.5 text-[11px] underline-offset-2 hover:underline">
                Manage
              </span>
            </button>
            <span className="text-muted">·</span>
            <button
              onClick={() =>
                shareModal.open({
                  stashId,
                  stashName: stash?.name,
                  tab: views.length > 0 ? "manage" : "new",
                })
              }
              title="View, create, or revoke share links"
              className="rounded-md px-1.5 py-0.5 hover:bg-raised"
            >
              <span aria-hidden>🔗</span>{" "}
              {views.length === 0
                ? "No share links"
                : `${views.length} share link${views.length === 1 ? "" : "s"}`}
            </button>
            <span className="text-muted">·</span>
            <span>updated {stash?.updated_at ? formatRelative(stash.updated_at) : ""}</span>
            <span className="text-muted">·</span>
            <span>{stash?.is_public ? "Public" : "Private"}</span>
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          {!isMember && stash && (
            <div className="mt-4 flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-[13px]">
              <span className="text-muted">You aren&apos;t a member of this stash.</span>
              <button
                onClick={handleJoin}
                className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              >
                Join stash
              </button>
            </div>
          )}

          {isMember && (
            <div className="mt-6">
              <StashQuickAdd stashId={stashId} user={user} onAdded={refreshSpine} />
            </div>
          )}

          {/* Get-started callout — only for empty stashes. */}
          {spine &&
            spine.sessions.length === 0 &&
            totalFolders === 0 &&
            totalPages === 0 &&
            totalFiles === 0 && (
              <div className="mt-8 rounded-xl border border-[var(--color-brand-200)] bg-[var(--color-brand-50)] p-5">
                <h3 className="font-display text-[18px] font-semibold text-foreground">
                  Welcome — here&apos;s how a stash works
                </h3>
                <p className="mt-2 text-[13.5px] leading-relaxed text-foreground/80">
                  Drop in anything above — a link, a note, or a file — and we&apos;ll file it into the
                  Hopper folder for you. Connect your agents via the Stash CLI and their sessions
                  appear under <span className="font-medium text-foreground">Sessions</span>; your
                  pages, files, and folders live in the <span className="font-medium text-foreground">Wiki</span>.
                  Share any part of it with a single link.
                </p>
              </div>
            )}

          {/* Handoff (orientation doc written by the sleep-time agent) */}
          {isMember && (
            <HandoffPanel
              stashId={stashId}
              canWrite={isMember}
              metadataHint={spine?.handoff_metadata}
            />
          )}

          {/* Sessions */}
          <SectionHeader
            icon={<SessionsIcon />}
            title="Sessions"
            subtitle="episodic"
            trailing={`${spine?.sessions.length ?? 0} transcript${
              spine?.sessions.length === 1 ? "" : "s"
            }`}
          />
          {sessions.length > 0 ? (
            <CardGrid items={sessions} hover="brand" />
          ) : (
            <EmptyState text="No sessions yet. Push agent transcripts via the CLI." />
          )}

          {/* Wiki */}
          <SectionHeader
            icon={<WikiIcon />}
            title="Wiki"
            subtitle="structured"
            trailing={`${totalFolders} folder${totalFolders === 1 ? "" : "s"} · ${
              totalPages
            } page${totalPages === 1 ? "" : "s"} · ${totalFiles} file${
              totalFiles === 1 ? "" : "s"
            }`}
          />
          {isMember && (
            <div className="mt-2 mb-3 flex flex-wrap items-center gap-2">
              <input ref={fileInputRef} type="file" className="hidden" onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  const uploaded = await uploadFile(stashId, file);
                  addFileToSpine(uploaded, setSpine);
                } catch { /* */ }
                if (fileInputRef.current) fileInputRef.current.value = "";
              }} />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + Upload file
              </button>
              <button
                onClick={async () => {
                  try {
                    const p = await createPage(stashId, "Untitled");
                    router.push(`/stashes/${stashId}/p/${p.id}`);
                  } catch { /* */ }
                }}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + New page
              </button>
              <button
                onClick={async () => {
                  const name = window.prompt("Folder name?");
                  if (!name?.trim()) return;
                  try {
                    const folder = await createFolder(stashId, name.trim());
                    addFolderToSpine(folder, setSpine);
                  } catch { /* */ }
                }}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + New folder
              </button>
            </div>
          )}
          {wikiItems.length > 0 ? (
            <CardGrid items={wikiItems} hover="brand" />
          ) : (
            <EmptyState text="Upload PDFs, sheets, or create wiki pages." />
          )}
        </div>
      </div>
      <MembersModal stashId={stashId} open={membersOpen} onClose={() => setMembersOpen(false)} />
    </>
  );
}

function SectionHeader({
  icon,
  title,
  subtitle,
  trailing,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  trailing: string;
}) {
  return (
    <div className="mt-8 flex items-baseline justify-between">
      <h2 className="flex items-baseline gap-2 font-display text-xl font-semibold text-foreground">
        <span className="inline-flex text-[22px] text-muted">{icon}</span>
        <span>
          {title}{" "}
          <span className="text-[12px] font-normal italic text-muted">· {subtitle}</span>
        </span>
      </h2>
      <span className="text-[11.5px] text-muted">{trailing}</span>
    </div>
  );
}

function EmptyState({
  text,
  action,
}: {
  text: string;
  action?: { href: string; label: string };
}) {
  return (
    <div className="mt-2 rounded-lg border border-dashed border-border bg-surface/30 px-4 py-6 text-center text-[12.5px] text-muted">
      {text}
      {action && (
        <div className="mt-2">
          <span className="font-mono text-[12px]">{action.label}</span>
        </div>
      )}
    </div>
  );
}

const AVATAR_PALETTE: { bg: string; fg: string }[] = [
  { bg: "bg-rose-200", fg: "text-rose-800" },
  { bg: "bg-indigo-200", fg: "text-indigo-800" },
  { bg: "bg-emerald-200", fg: "text-emerald-800" },
  { bg: "bg-amber-200", fg: "text-amber-900" },
  { bg: "bg-sky-200", fg: "text-sky-800" },
  { bg: "bg-fuchsia-200", fg: "text-fuchsia-800" },
];

function avatarFor(name: string) {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = (h * 33 + name.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
}

function MemberStack({ members }: { members: WorkspaceMember[] }) {
  if (!members.length) return null;
  const display = members.slice(0, 5);
  const overflow = members.length - display.length;
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex -space-x-1.5">
        {display.map((m) => {
          const label = (m.display_name || m.name || "?").trim();
          const palette = avatarFor(label);
          return (
            <span
              key={m.user_id}
              className={
                "inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-base text-[9.5px] font-semibold " +
                palette.bg +
                " " +
                palette.fg
              }
              title={`${label}${m.role && m.role !== "editor" ? ` · ${m.role}` : ""}`}
            >
              {label.slice(0, 2).toUpperCase()}
            </span>
          );
        })}
      </div>
      {overflow > 0 && <span className="text-[11px] text-muted">+{overflow}</span>}
      <span className="text-[12px] text-muted">
        {members.length} member{members.length !== 1 ? "s" : ""}
      </span>
    </div>
  );
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function addFolderToSpine(
  folder: Folder,
  setSpine: Dispatch<SetStateAction<StashOverview | null>>
) {
  setSpine((current) => {
    if (!current) return current;
    const folders = [
      ...current.wiki.folders,
      {
        id: folder.id,
        name: folder.name,
        parent_folder_id: folder.parent_folder_id,
        page_count: 0,
        file_count: 0,
        has_skill: false,
      },
    ].sort((a, b) => a.name.localeCompare(b.name));

    return { ...current, wiki: { ...current.wiki, folders } };
  });
}

function addFileToSpine(
  file: FileInfo,
  setSpine: Dispatch<SetStateAction<StashOverview | null>>
) {
  setSpine((current) => {
    if (!current) return current;
    const nextFile: WikiFile = {
      id: file.id,
      name: file.name,
      folder_id: file.folder_id ?? null,
      size_bytes: file.size_bytes,
      content_type: file.content_type,
      url: file.url,
      created_at: file.created_at,
      linked_table_id: file.linked_table_id ?? null,
    };

    return {
      ...current,
      wiki: {
        ...current.wiki,
        files: [nextFile, ...current.wiki.files],
      },
    };
  });
}

// Inline-editable description on the stash home. Backs the handoff
// writer's `description` seed input — the stash owner's only freeform
// hint about what the stash is for.
function StashDescription({
  stash,
  canEdit,
  onSaved,
}: {
  stash: Workspace | null;
  canEdit: boolean;
  onSaved: (updated: Workspace) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!stash) return null;

  const description = stash.description ?? "";

  function startEdit() {
    setDraft(description);
    setError("");
    setEditing(true);
  }

  async function save() {
    if (!stash) return;
    setBusy(true);
    setError("");
    try {
      const updated = await updateWorkspace(stash.id, { description: draft });
      onSaved(updated);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <div className="mt-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={1000}
          rows={4}
          className="w-full rounded-md border border-border bg-base p-2 text-[14px] leading-relaxed"
          placeholder="What is this stash for? Anything the handoff writer should treat as authoritative."
        />
        {error && <div className="mt-1 text-[11.5px] text-red-700">{error}</div>}
        <div className="mt-1.5 flex items-center gap-2 text-[11.5px] text-muted">
          <button
            onClick={save}
            disabled={busy}
            className="rounded-md bg-[var(--color-brand-600)] px-2.5 py-1 font-medium text-white hover:bg-[var(--color-brand-700)] disabled:opacity-60"
          >
            {busy ? "Saving…" : "Save description"}
          </button>
          <button
            onClick={() => setEditing(false)}
            disabled={busy}
            className="rounded-md border border-border px-2.5 py-1 hover:bg-base"
          >
            Cancel
          </button>
          <span className="ml-auto">{draft.length}/1000</span>
        </div>
      </div>
    );
  }

  if (description) {
    return (
      <p className="group/desc mt-2 text-[14.5px] leading-relaxed text-muted">
        {description}
        {canEdit && (
          <button
            onClick={startEdit}
            className="ml-2 align-middle text-[11.5px] text-muted opacity-0 underline-offset-2 hover:underline group-hover/desc:opacity-100"
          >
            Edit
          </button>
        )}
      </p>
    );
  }

  if (!canEdit) return null;

  return (
    <button
      onClick={startEdit}
      className="mt-2 text-[12.5px] italic text-muted underline-offset-2 hover:underline"
    >
      + Add a description — tell the handoff writer what this stash is for.
    </button>
  );
}
