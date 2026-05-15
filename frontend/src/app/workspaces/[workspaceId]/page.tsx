"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import MembersModal from "../../../components/MembersModal";
import SessionUpload from "../../../components/SessionUpload";
import StashQuickAdd from "../../../components/StashQuickAdd";
import {
  FileIcon,
  FolderIcon,
  PageIcon,
  SessionsIcon,
  StashIcon,
  TableIcon,
} from "../../../components/StashIcons";
import { useAuth } from "../../../hooks/useAuth";
import {
  createFolder,
  createPage,
  getWorkspaceOverview,
  getWorkspace,
  getWorkspaceMembers,
  joinWorkspace,
  listStashes,
  updateWorkspace,
  uploadFile,
  type WorkspaceOverview,
  type WorkspaceFile,
  type WorkspaceStash,
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

export default function WorkspaceHomePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const { user, loading, logout } = useAuth();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [spine, setSpine] = useState<WorkspaceOverview | null>(null);
  const [stashes, setStashes] = useState<WorkspaceStash[]>([]);
  const [error, setError] = useState("");
  const [membersOpen, setMembersOpen] = useState(false);
  const shareModal = useShareModal();
  const shareVersion = shareModal.version;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const [workspaceResult, membersResult, spineResult, stashesResult] = await Promise.allSettled([
      getWorkspace(workspaceId),
      getWorkspaceMembers(workspaceId),
      getWorkspaceOverview(workspaceId),
      listStashes(workspaceId),
    ]);

    if (workspaceResult.status === "fulfilled") {
      setWorkspace(workspaceResult.value);
    } else {
      setError("Workspace not found");
    }

    if (membersResult.status === "fulfilled") {
      setMembers(membersResult.value);
    }

    if (spineResult.status === "fulfilled") {
      setSpine(spineResult.value);
    }

    if (stashesResult.status === "fulfilled") {
      setStashes(stashesResult.value);
    }
  }, [workspaceId]);

  const refreshSpine = useCallback(async () => {
    try {
      setSpine(await getWorkspaceOverview(workspaceId));
    } catch {
      /* private */
    }
  }, [workspaceId]);

  useEffect(() => {
    if (!user) return;
    load();
  }, [user, load, shareVersion]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  const isMember = !!user && members.some((m) => m.user_id === user.id);

  async function handleJoin() {
    if (!workspace) return;
    try {
      await joinWorkspace(workspace.invite_code);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to join");
    }
  }

  if (loading)
    return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;
  if (!user) return null;

  const sessions: CardItem[] = (spine?.sessions ?? []).slice(0, 6).map((s) => ({
    href: `/workspaces/${workspaceId}/sessions/${encodeURIComponent(s.session_id)}`,
    icon: <SessionsIcon />,
    title: `#${s.session_id.length > 28 ? s.session_id.slice(0, 28) + "…" : s.session_id}`,
    subtitle: `${s.agent_name} · ${formatBytes(s.size_bytes)}`,
  }));

  // Root-level file contents only. Nested folders/pages/files surface
  // through their parent folder's detail page, not here.
  const filesTree = spine?.files;
  const rootFolders = (filesTree?.folders ?? []).filter((f) => !f.parent_folder_id);
  const rootPages = (filesTree?.pages ?? []).filter((p) => !p.folder_id);
  const rootFiles = (filesTree?.files ?? []).filter((f) => !f.folder_id);

  const folderItems: CardItem[] = rootFolders.map((f) => ({
    href: `/workspaces/${workspaceId}/folders/${f.id}`,
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
  const pageItems: CardItem[] = rootPages.map((p) => ({
    href: `/workspaces/${workspaceId}/p/${p.id}`,
    icon: <PageIcon />,
    title: p.name.replace(/\.md$/, ""),
    subtitle: "Page",
  }));
  const fileItems: CardItem[] = rootFiles.slice(0, 12).map((f) => {
    const isCsvLinked = f.content_type?.includes("csv") && f.linked_table_id;
    return {
      href: isCsvLinked
        ? `/tables/${f.linked_table_id}?workspaceId=${workspaceId}`
        : `/workspaces/${workspaceId}/f/${f.id}`,
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
  const filesItems = [...folderItems, ...pageItems, ...fileItems];
  const totalFolders = filesTree?.folders.length ?? 0;
  const totalPages = filesTree?.pages.length ?? 0;
  const totalFiles = filesTree?.files.length ?? 0;

  return (
    <>
      <div className="scroll-thin flex-1 overflow-y-auto">
        <div
          className="h-32 bg-gradient-to-r from-[var(--color-brand-200)] via-amber-100 to-rose-100 bg-cover bg-center"
          style={
            workspace?.cover_image_url
              ? { backgroundImage: `url(${workspace.cover_image_url})` }
              : workspace?.color_gradient
              ? { backgroundImage: workspace.color_gradient }
              : undefined
          }
        />
        <div className="mx-auto -mt-8 max-w-3xl px-12 pb-16">
          <div className="mb-2 flex h-12 w-12 items-center justify-center overflow-hidden text-5xl text-[var(--color-brand-700)]">
            {workspace?.icon_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={workspace.icon_url} alt="" className="h-12 w-12 rounded-lg object-cover" />
            ) : (
              <StashIcon />
            )}
          </div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-[34px] font-bold tracking-tight text-foreground">
              {workspace?.name || "Loading…"}
            </h1>
            {isMember && (
              <Link
                href={`/workspaces/${workspaceId}/settings`}
                title="Workspace settings"
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
            workspace={workspace}
            canEdit={isMember}
            onSaved={(updated) => setWorkspace(updated)}
          />


          <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <button
              onClick={() => setMembersOpen(true)}
              title="View, add, or remove members"
              className="rounded-md px-1.5 py-0.5 hover:bg-raised"
            >
              <MemberStack members={members} />
              <span className="ml-1.5 text-[11px] underline-offset-2 hover:underline">
                Members
              </span>
            </button>
            <span className="text-muted">·</span>
            <button
              onClick={() =>
                shareModal.open({
                  workspaceId,
                  workspaceName: workspace?.name,
                  tab: stashes.length > 0 ? "manage" : "new",
                })
              }
              title="View, create, or revoke stashes"
              className="rounded-md px-1.5 py-0.5 hover:bg-raised"
            >
              <span aria-hidden>🔗</span>{" "}
              {stashes.length === 0
                ? "No stashes"
                : `${stashes.length} stash${stashes.length === 1 ? "" : "es"}`}
            </button>
            <span className="text-muted">·</span>
            <span>updated {workspace?.updated_at ? formatRelative(workspace.updated_at) : ""}</span>
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-300/40 bg-red-500/10 px-4 py-2 text-[13px] text-red-500">
              {error}
            </div>
          )}

          {!isMember && workspace && (
            <div className="mt-4 flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 text-[13px]">
              <span className="text-muted">You aren&apos;t a member of this workspace.</span>
              <button
                onClick={handleJoin}
                className="rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[var(--color-brand-700)]"
              >
                Join workspace
              </button>
            </div>
          )}

          {isMember && (
            <div className="mt-6">
              <StashQuickAdd workspaceId={workspaceId} user={user} onAdded={refreshSpine} />
            </div>
          )}

          {/* Get-started callout — only for an empty workspace. */}
          {spine &&
            spine.sessions.length === 0 &&
            totalFolders === 0 &&
            totalPages === 0 &&
            totalFiles === 0 && (
              <div className="mt-8 rounded-xl border border-[var(--color-brand-200)] bg-[var(--color-brand-50)] p-5">
                <h3 className="font-display text-[18px] font-semibold text-foreground">
                  Welcome — here&apos;s how a workspace works
                </h3>
                <p className="mt-2 text-[13.5px] leading-relaxed text-foreground/80">
                  Drop in anything above — a link, a note, or a file — and we&apos;ll file it into the
                  Hopper folder for you. Connect your agents via the Stash CLI and their sessions
                  appear under <span className="font-medium text-foreground">Sessions</span>; your
                  pages, files, and folders live in <span className="font-medium text-foreground">Files</span>.
                  Bundle any set of pages and sessions into a Stash when you need to publish or hand off context.
                </p>
              </div>
            )}

          {/* Sessions */}
          <SectionHeader
            icon={<SessionsIcon />}
            title="Sessions"
            trailing={`${spine?.sessions.length ?? 0} transcript${
              spine?.sessions.length === 1 ? "" : "s"
            }`}
          />
          {isMember && (
            <div className="mt-2 mb-3">
              <SessionUpload workspaceId={workspaceId} onUploaded={load} />
            </div>
          )}
          {sessions.length > 0 ? (
            <CardGrid items={sessions} hover="brand" />
          ) : (
            <EmptyState text="No sessions yet. Push agent transcripts via the CLI." />
          )}

          {/* Files */}
          <SectionHeader
            icon={<FileIcon />}
            title="Files"
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
                  const uploaded = await uploadFile(workspaceId, file);
                  addFileToSpine(uploaded, setSpine);
                } catch { /* */ }
                if (fileInputRef.current) fileInputRef.current.value = "";
              }} />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + Add page or file
              </button>
              <button
                onClick={async () => {
                  try {
                    const p = await createPage(workspaceId, "Untitled");
                    router.push(`/workspaces/${workspaceId}/p/${p.id}`);
                  } catch { /* */ }
                }}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + Add page
              </button>
              <button
                onClick={async () => {
                  const name = window.prompt("Folder name?");
                  if (!name?.trim()) return;
                  try {
                    const folder = await createFolder(workspaceId, name.trim());
                    addFolderToSpine(folder, setSpine);
                  } catch { /* */ }
                }}
                className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-foreground hover:bg-raised"
              >
                + New folder
              </button>
            </div>
          )}
          {filesItems.length > 0 ? (
            <CardGrid items={filesItems} hover="brand" />
          ) : (
            <EmptyState text="Upload files or create pages." />
          )}

          <SectionHeader
            icon={<StashIcon />}
            title="Stashes"
            trailing={`${stashes.length} stash${stashes.length === 1 ? "" : "es"}`}
          />
          {isMember && (
            <button
              onClick={() =>
                shareModal.open({
                  workspaceId,
                  workspaceName: workspace?.name,
                  tab: "new",
                })
              }
              className="mt-2 rounded-md bg-[var(--color-brand-600)] px-3 py-1.5 text-[13px] font-medium text-white hover:bg-[var(--color-brand-700)]"
            >
              + Add stash
            </button>
          )}
          {stashes.length > 0 ? (
            <CardGrid
              items={stashes.slice(0, 8).map((stash) => ({
                href: `/stashes/${stash.slug}`,
                icon: <StashIcon />,
                title: stash.title,
                subtitle: `${stash.items.length} item${
                  stash.items.length === 1 ? "" : "s"
                }`,
              }))}
              hover="indigo"
            />
          ) : (
            <EmptyState text="Create a Stash to bundle sessions and files." />
          )}
        </div>
      </div>
      <MembersModal workspaceId={workspaceId} open={membersOpen} onClose={() => setMembersOpen(false)} />
    </>
  );
}

function SectionHeader({
  icon,
  title,
  trailing,
}: {
  icon: React.ReactNode;
  title: string;
  trailing: string;
}) {
  return (
    <div className="mt-8 flex items-baseline justify-between">
      <h2 className="flex items-baseline gap-2 font-display text-xl font-semibold text-foreground">
        <span className="inline-flex text-[22px] text-muted">{icon}</span>
        <span>{title}</span>
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
  setSpine: Dispatch<SetStateAction<WorkspaceOverview | null>>
) {
  setSpine((current) => {
    if (!current) return current;
    if (!current.files) return current;
    const folders = [
      ...current.files.folders,
      {
        id: folder.id,
        name: folder.name,
        parent_folder_id: folder.parent_folder_id,
        page_count: 0,
        file_count: 0,
        has_skill: false,
      },
    ].sort((a, b) => a.name.localeCompare(b.name));

    return { ...current, files: { ...current.files, folders } };
  });
}

function addFileToSpine(
  file: FileInfo,
  setSpine: Dispatch<SetStateAction<WorkspaceOverview | null>>
) {
  setSpine((current) => {
    if (!current) return current;
    if (!current.files) return current;
    const nextFile: WorkspaceFile = {
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
      files: {
        ...current.files,
        files: [nextFile, ...current.files.files],
      },
    };
  });
}

// Inline-editable description on the workspace home.
function StashDescription({
  workspace,
  canEdit,
  onSaved,
}: {
  workspace: Workspace | null;
  canEdit: boolean;
  onSaved: (updated: Workspace) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!workspace) return null;

  const description = workspace.description ?? "";

  function startEdit() {
    setDraft(description);
    setError("");
    setEditing(true);
  }

  async function save() {
    if (!workspace) return;
    setBusy(true);
    setError("");
    try {
      const updated = await updateWorkspace(workspace.id, { description: draft });
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
          placeholder="What is this workspace for?"
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
      + Add a description
    </button>
  );
}
