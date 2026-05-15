"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type DragEvent } from "react";
import { usePathname } from "next/navigation";
import {
  type FolderContents,
  type WorkspaceFile,
  type WorkspaceSidebar,
  uploadFile,
  uploadTranscript,
} from "../lib/api";
import {
  getCachedFolderContents,
  getCachedWorkspaceSidebar,
  getCachedWorkspaces,
  readCachedFolderContents,
  readCachedSidebars,
  readCachedWorkspaces,
  refreshWorkspaceSidebar,
} from "../lib/stashNavigationCache";
import type { User, Workspace } from "../lib/types";
import {
  ActivityIcon,
  DiscoverIcon,
  FileIcon,
  FolderIcon,
  HelpIcon,
  PageIcon,
  SessionsIcon,
  SettingsIcon,
  StashIcon,
  TableIcon,
} from "./StashIcons";

interface AppSidebarProps {
  user?: User;
  onLogout?: () => void;
  cmdkOpen?: boolean;
  onCmdkOpen?: () => void;
}

interface WorkspaceNode extends Workspace {
  shared?: boolean;
}

type SidebarSection = "sessions" | "files" | "stashes";
type DropSection = "sessions" | "files";
type DropStatus = "idle" | "over" | "saving" | "done" | "error";

interface SidebarDropState {
  key: string | null;
  status: DropStatus;
  message: string;
}

const OPEN_WORKSPACES_KEY = "stash_sidebar_open_workspaces";
const OPEN_SECTIONS_KEY = "stash_sidebar_open_sections";

function readOpenMap(key: string): Record<string, boolean> {
  if (typeof window === "undefined") return {};

  const raw = window.localStorage.getItem(key);
  if (!raw) return {};

  return JSON.parse(raw);
}

function writeOpenMap(key: string, value: Record<string, boolean>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function sectionKey(workspaceId: string, section: SidebarSection): string {
  return `${workspaceId}:${section}`;
}

function dropKey(workspaceId: string, section: DropSection): string {
  return `${workspaceId}:${section}`;
}

function isFilesDrag(event: DragEvent<HTMLElement>): boolean {
  return Array.from(event.dataTransfer.types).includes("Files");
}

function isJsonl(file: File): boolean {
  return file.name.toLowerCase().endsWith(".jsonl");
}

function sessionIdFromFile(file: File): string {
  return file.name.replace(/\.jsonl$/i, "").trim();
}

function ChevronToggle({ onToggle }: { onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
      className="-ml-0.5 flex h-4 w-4 items-center justify-center rounded text-muted hover:bg-base/60 hover:text-foreground"
      aria-label="Toggle"
    >
      <svg
        className="chev h-3 w-3"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
    </button>
  );
}

function NavRow({
  href,
  icon,
  label,
  active,
  trailing,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  trailing?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={
        "page-row flex items-center gap-2 rounded-md px-2 py-1 text-[13px] transition-colors " +
        (active
          ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)]"
          : "text-dim hover:bg-raised hover:text-foreground")
      }
    >
      <span className="flex h-4 w-4 items-center justify-center text-[14px]">{icon}</span>
      <span className="flex-1 truncate">{label}</span>
      {trailing}
    </Link>
  );
}

function WorkspaceTree({
  workspace,
  spine,
  open,
  onOpenChange,
  openSections,
  onSectionOpenChange,
  pathname,
  dropState,
  onDropFiles,
  onDropHover,
}: {
  workspace: WorkspaceNode;
  spine: WorkspaceSidebar | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  openSections: Record<SidebarSection, boolean>;
  onSectionOpenChange: (section: SidebarSection, open: boolean) => void;
  pathname: string;
  dropState: SidebarDropState;
  onDropFiles: (workspaceId: string, section: DropSection, files: FileList) => void;
  onDropHover: (workspaceId: string, section: DropSection, active: boolean) => void;
}) {
  const isActive = pathname === `/workspaces/${workspace.id}`;
  const dropProps = (section: DropSection) => ({
    onDragOver(event: DragEvent<HTMLElement>) {
      if (!isFilesDrag(event)) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "copy";
      onDropHover(workspace.id, section, true);
    },
    onDragLeave(event: DragEvent<HTMLElement>) {
      if (!isFilesDrag(event)) return;
      event.preventDefault();
      event.stopPropagation();
      onDropHover(workspace.id, section, false);
    },
    onDrop(event: DragEvent<HTMLElement>) {
      if (!isFilesDrag(event)) return;
      event.preventDefault();
      event.stopPropagation();
      onDropFiles(workspace.id, section, event.dataTransfer.files);
    },
  });
  const sessionsDrop = dropState.key === dropKey(workspace.id, "sessions") ? dropState : null;

  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="group/workspace"
    >
      <summary
        onClick={(e) => e.preventDefault()}
        className="page-row flex items-center gap-1 rounded-md px-2 py-1 text-[13px] hover:bg-raised"
      >
        <ChevronToggle onToggle={() => onOpenChange(!open)} />
        <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
          <StashIcon />
        </span>
        <Link
          href={`/workspaces/${workspace.id}`}
          className={
            "flex-1 truncate font-medium " +
            (isActive ? "text-[var(--color-brand-800)]" : "text-foreground")
          }
        >
          {workspace.name}
        </Link>
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        <NavRow
          href={`/workspaces/${workspace.id}`}
          icon={<StashIcon />}
          label="Home"
          active={pathname === `/workspaces/${workspace.id}`}
        />
        <NavRow
          href={`/activity?workspace=${workspace.id}`}
          icon={<ActivityIcon />}
          label="Activity"
        />
        <details
          open={openSections.sessions}
          onToggle={(e) => onSectionOpenChange("sessions", e.currentTarget.open)}
          className="text-[13px]"
          {...dropProps("sessions")}
        >
          <summary
            onClick={(e) => e.preventDefault()}
            className={
              "page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised " +
              (sessionsDrop?.status === "over"
                ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)] ring-1 ring-[var(--color-brand-300)]"
                : "")
            }
          >
            <ChevronToggle
              onToggle={() => onSectionOpenChange("sessions", !openSections.sessions)}
            />
            <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
              <SessionsIcon />
            </span>
            <Link
              href={`/workspaces/${workspace.id}/sessions`}
              className="flex-1 truncate font-medium text-foreground hover:text-[var(--color-brand-700)]"
            >
              Sessions
            </Link>
            <span className="text-[10.5px] text-muted">{spine?.sessions.length ?? 0}</span>
          </summary>
          <div className="ml-3 space-y-0.5 border-l border-border pl-2">
            {sessionsDrop?.message ? <DropMessage state={sessionsDrop} /> : null}
            {spine?.sessions.slice(0, 8).map((s) => (
              <NavRow
                key={s.session_id}
                href={`/workspaces/${workspace.id}/sessions/${encodeURIComponent(s.session_id)}`}
                icon={<span className="text-muted">#</span>}
                label={s.session_id.length > 22 ? s.session_id.slice(0, 22) + "…" : s.session_id}
              />
            ))}
            {(!spine || spine.sessions.length === 0) && (
              <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
            )}
          </div>
        </details>

        <FilesBlock
          workspace={workspace}
          spine={spine}
          open={openSections.files}
          onOpenChange={(nextOpen) => onSectionOpenChange("files", nextOpen)}
          dropState={dropState}
          dropProps={dropProps("files")}
        />
        <StashesBlock
          spine={spine}
          open={openSections.stashes}
          onOpenChange={(nextOpen) => onSectionOpenChange("stashes", nextOpen)}
        />
      </div>
    </details>
  );
}

function fileIconClass(contentType: string | undefined): string {
  if (contentType?.includes("pdf")) return "text-rose-500";
  if (contentType?.includes("csv")) return "text-emerald-600";
  if (contentType?.includes("html")) return "text-amber-600";
  return "text-muted";
}

function FileNavRow({
  workspaceId,
  file,
}: {
  workspaceId: string;
  file: Pick<WorkspaceFile, "id" | "name" | "content_type" | "linked_table_id">;
}) {
  const isCsvLinked =
    file.content_type?.includes("csv") && file.linked_table_id;
  const href = isCsvLinked
    ? `/tables/${file.linked_table_id}?workspaceId=${workspaceId}`
    : `/workspaces/${workspaceId}/f/${file.id}`;
  return (
    <NavRow
      href={href}
      icon={
        <span className={fileIconClass(file.content_type)}>
          {file.content_type?.includes("csv") ? <TableIcon /> : <FileIcon />}
        </span>
      }
      label={file.name}
    />
  );
}

function DropMessage({ state }: { state: SidebarDropState }) {
  const tone =
    state.status === "error"
      ? "text-red-600"
      : state.status === "done"
        ? "text-[var(--color-brand-700)]"
        : "text-muted";

  return (
    <div className={"px-2 py-1 text-[11px] " + tone}>
      {state.message}
    </div>
  );
}

function FolderTreeNode({
  workspaceId,
  folderId,
  name,
}: {
  workspaceId: string;
  folderId: string;
  name: string;
}) {
  const cachedContents = readCachedFolderContents(folderId);
  const [contents, setContents] = useState<FolderContents | null>(cachedContents);
  const [loaded, setLoaded] = useState(!!cachedContents);
  const [open, setOpen] = useState(false);

  const handleToggle = useCallback(() => {
    const next = !open;
    setOpen(next);
    if (next && !loaded) {
      setLoaded(true);
      getCachedFolderContents(workspaceId, folderId)
        .then(setContents)
        .catch(() =>
          setContents({
            folder: { id: folderId, name, parent_folder_id: null },
            breadcrumbs: [],
            subfolders: [],
            pages: [],
            files: [],
          })
        );
    }
  }, [open, loaded, workspaceId, folderId, name]);

  return (
    <details open={open} className="text-[12.5px]">
      <summary
        onClick={(e) => e.preventDefault()}
        className="page-row flex items-center gap-1 rounded-md px-2 py-0.5 hover:bg-raised"
      >
        <ChevronToggle onToggle={handleToggle} />
        <span className="flex h-4 w-4 items-center justify-center text-muted">
          <FolderIcon />
        </span>
        <Link
          href={`/workspaces/${workspaceId}/folders/${folderId}`}
          className="flex-1 truncate text-left text-foreground hover:text-[var(--color-brand-700)]"
        >
          {name}
        </Link>
      </summary>
      <div className="ml-2.5 space-y-0.5 border-l border-border pl-2">
        {contents === null && loaded && (
          <div className="px-2 py-1 text-[11px] italic text-muted">loading…</div>
        )}
        {contents?.subfolders.map((sub) => (
          <FolderTreeNode
            key={sub.id}
            workspaceId={workspaceId}
            folderId={sub.id}
            name={sub.name}
          />
        ))}
        {contents?.pages.map((p) => (
          <NavRow
            key={p.id}
            href={`/workspaces/${workspaceId}/p/${p.id}`}
            icon={<PageIcon className="text-muted" />}
            label={p.name}
          />
        ))}
        {contents?.files.map((f) => (
          <FileNavRow key={f.id} workspaceId={workspaceId} file={f} />
        ))}
        {contents &&
          contents.subfolders.length === 0 &&
          contents.pages.length === 0 &&
          contents.files.length === 0 && (
            <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
          )}
      </div>
    </details>
  );
}

function FilesBlock({
  workspace,
  spine,
  open,
  onOpenChange,
  dropState,
  dropProps,
}: {
  workspace: WorkspaceNode;
  spine: WorkspaceSidebar | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dropState: SidebarDropState;
  dropProps: {
    onDragOver: (event: DragEvent<HTMLElement>) => void;
    onDragLeave: (event: DragEvent<HTMLElement>) => void;
    onDrop: (event: DragEvent<HTMLElement>) => void;
  };
}) {
  const tree = spine?.files;
  const folders = tree?.folders ?? [];
  const pages = tree?.pages ?? [];
  const files = tree?.files ?? [];
  const rootFolders = folders.filter((f) => !f.parent_folder_id);
  const rootPages = pages.filter((p) => !p.folder_id);
  const rootFiles = files.filter((f) => !f.folder_id);
  const total = folders.length + pages.length + files.length;
  const filesDrop = dropState.key === dropKey(workspace.id, "files") ? dropState : null;
  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="text-[13px]"
      {...dropProps}
    >
      <summary
        onClick={(e) => {
          e.preventDefault();
          onOpenChange(!open);
        }}
        className={
          "page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised " +
          (filesDrop?.status === "over"
            ? "bg-[var(--color-brand-50)] text-[var(--color-brand-800)] ring-1 ring-[var(--color-brand-300)]"
            : "")
        }
      >
        <ChevronToggle onToggle={() => onOpenChange(!open)} />
        <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
          <FileIcon />
        </span>
        <span className="flex-1 truncate font-medium text-foreground">Files</span>
        <span className="text-[10.5px] text-muted">{total}</span>
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        {filesDrop?.message ? <DropMessage state={filesDrop} /> : null}
        {rootFolders.map((f) => (
          <FolderTreeNode
            key={f.id}
            workspaceId={workspace.id}
            folderId={f.id}
            name={f.name}
          />
        ))}
        {rootPages.slice(0, 10).map((p) => (
          <NavRow
            key={p.id}
            href={`/workspaces/${workspace.id}/p/${p.id}`}
            icon={<PageIcon className="text-muted" />}
            label={p.name}
          />
        ))}
        {rootFiles.slice(0, 12).map((f) => (
          <FileNavRow key={f.id} workspaceId={workspace.id} file={f} />
        ))}
        {!spine || total === 0 ? (
          <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
        ) : null}
      </div>
    </details>
  );
}

function StashesBlock({
  spine,
  open,
  onOpenChange,
}: {
  spine: WorkspaceSidebar | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const stashes = spine?.stashes ?? [];
  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="text-[13px]"
    >
      <summary
        onClick={(e) => {
          e.preventDefault();
          onOpenChange(!open);
        }}
        className="page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised"
      >
        <ChevronToggle onToggle={() => onOpenChange(!open)} />
        <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
          <StashIcon />
        </span>
        <span className="flex-1 truncate font-medium text-foreground">Stashes</span>
        <span className="text-[10.5px] text-muted">{stashes.length}</span>
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        {stashes.slice(0, 12).map((stash) => (
          <NavRow
            key={stash.id}
            href={`/stashes/${stash.slug}`}
            icon={<StashIcon />}
            label={stash.title}
            trailing={
              stash.is_external ? <span className="text-[10px] text-muted">ext</span> : null
            }
          />
        ))}
        {stashes.length === 0 ? (
          <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
        ) : null}
      </div>
    </details>
  );
}

export default function AppSidebar({ user, onCmdkOpen }: AppSidebarProps) {
  const pathname = usePathname();
  const userId = user?.id;
  const cachedWorkspaces = readCachedWorkspaces(userId);
  const activeTreeMatch = pathname.match(
    /^\/workspaces\/([^/]+)\/(sessions|folders|p|f|stashes)(?:\/|$)/
  );
  const activeTreeWorkspaceId = activeTreeMatch?.[1] ?? null;
  const activeTreeSection: SidebarSection | null =
    activeTreeMatch?.[2] === "sessions"
      ? "sessions"
      : activeTreeMatch?.[2] === "stashes"
        ? "stashes"
      : activeTreeMatch
        ? "files"
        : null;
  const [mine, setMine] = useState<Workspace[]>(cachedWorkspaces?.mine ?? []);
  const [shared, setShared] = useState<Workspace[]>(cachedWorkspaces?.shared ?? []);
  const [openWorkspaces, setOpenWorkspaces] = useState<Record<string, boolean>>(() =>
    readOpenMap(OPEN_WORKSPACES_KEY)
  );
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() =>
    readOpenMap(OPEN_SECTIONS_KEY)
  );
  const [spines, setSpines] = useState<Record<string, WorkspaceSidebar>>(() =>
    readCachedSidebars()
  );
  const [dropState, setDropState] = useState<SidebarDropState>({
    key: null,
    status: "idle",
    message: "",
  });

  useEffect(() => {
    if (!userId) return;

    getCachedWorkspaces(userId)
      .then((r) => {
        setMine(r.mine);
        setShared(r.shared);
      })
      .catch(() => {});
  }, [userId]);

  const setOpenWorkspace = useCallback((workspaceId: string, open: boolean) => {
    setOpenWorkspaces((current) => {
      const next = { ...current, [workspaceId]: open };
      writeOpenMap(OPEN_WORKSPACES_KEY, next);
      return next;
    });
  }, []);

  const setOpenSection = useCallback((
    workspaceId: string,
    section: SidebarSection,
    open: boolean
  ) => {
    setOpenSections((current) => {
      const next = { ...current, [sectionKey(workspaceId, section)]: open };
      writeOpenMap(OPEN_SECTIONS_KEY, next);
      return next;
    });
  }, []);

  useEffect(() => {
    const openIds = Object.keys(openWorkspaces).filter((workspaceId) => openWorkspaces[workspaceId]);
    if (activeTreeWorkspaceId) openIds.push(activeTreeWorkspaceId);

    Array.from(new Set(openIds))
      .filter((workspaceId) => !spines[workspaceId])
      .forEach((workspaceId) => {
        getCachedWorkspaceSidebar(workspaceId)
          .then((sp) => setSpines((all) => ({ ...all, [workspaceId]: sp })))
          .catch(() => {});
      });
  }, [activeTreeWorkspaceId, openWorkspaces, spines]);

  function sectionOpen(workspaceId: string, section: SidebarSection): boolean {
    // Explicit user preference (open or closed) wins. Otherwise fall back to
    // route-derived open (so the active page's accordion expands by default).
    const explicit = openSections[sectionKey(workspaceId, section)];
    if (explicit !== undefined) return explicit;
    return activeTreeWorkspaceId === workspaceId && activeTreeSection === section;
  }

  function getOpenSections(workspaceId: string): Record<SidebarSection, boolean> {
    return {
      sessions: sectionOpen(workspaceId, "sessions"),
      files: sectionOpen(workspaceId, "files"),
      stashes: sectionOpen(workspaceId, "stashes"),
    };
  }

  function isWorkspaceOpen(workspaceId: string): boolean {
    const explicit = openWorkspaces[workspaceId];
    if (explicit !== undefined) return explicit;
    return activeTreeWorkspaceId === workspaceId;
  }

  function handleWorkspaceOpenChange(workspaceId: string, open: boolean) {
    // Skip persisting the auto-open that fires when a route activates this
    // workspace and no explicit user preference exists yet. Otherwise route nav
    // would write a "true" override that survives forever.
    const explicit = openWorkspaces[workspaceId];
    const routeOpen = activeTreeWorkspaceId === workspaceId;
    if (open && routeOpen && explicit === undefined) return;
    setOpenWorkspace(workspaceId, open);
  }

  function handleSectionOpenChange(
    workspaceId: string,
    section: SidebarSection,
    open: boolean
  ) {
    const explicit = openSections[sectionKey(workspaceId, section)];
    const routeOpen =
      activeTreeWorkspaceId === workspaceId && activeTreeSection === section;
    if (open && routeOpen && explicit === undefined) return;
    setOpenSection(workspaceId, section, open);
  }

  function clearDropLater(workspaceId: string, section: DropSection) {
    window.setTimeout(() => {
      setDropState((current) =>
        current.key === dropKey(workspaceId, section)
          ? { key: null, status: "idle", message: "" }
          : current
      );
    }, 2500);
  }

  function handleDropHover(workspaceId: string, section: DropSection, active: boolean) {
    const key = dropKey(workspaceId, section);
    setDropState((current) => {
      if (!active && current.key === key && current.status === "over") {
        return { key: null, status: "idle", message: "" };
      }
      if (!active) return current;
      return {
        key,
        status: "over",
        message:
          section === "sessions"
            ? "Drop .jsonl transcripts"
            : "Drop files into Files",
      };
    });
  }

  async function refreshSidebar(workspaceId: string) {
    const sidebar = await refreshWorkspaceSidebar(workspaceId);
    setSpines((all) => ({ ...all, [workspaceId]: sidebar }));
  }

  async function handleDropFiles(workspaceId: string, section: DropSection, files: FileList) {
    const list = Array.from(files);
    const key = dropKey(workspaceId, section);
    if (list.length === 0) return;

    if (section === "sessions") {
      const badFile = list.find((file) => !isJsonl(file));
      if (badFile) {
        setDropState({
          key,
          status: "error",
          message: "Sessions only accept .jsonl transcripts.",
        });
        clearDropLater(workspaceId, section);
        return;
      }

      const badSession = list.find((file) => !sessionIdFromFile(file));
      if (badSession) {
        setDropState({
          key,
          status: "error",
          message: "Transcript filename must include a session id.",
        });
        clearDropLater(workspaceId, section);
        return;
      }
    }

    setDropState({
      key,
      status: "saving",
      message: list.length === 1 ? `Uploading ${list[0].name}...` : `Uploading ${list.length} files...`,
    });

    try {
      if (section === "sessions") {
        for (const file of list) {
          await uploadTranscript(workspaceId, file, sessionIdFromFile(file), "manual-upload");
        }
      } else {
        for (const file of list) {
          await uploadFile(workspaceId, file);
        }
      }
      await refreshSidebar(workspaceId);
    } catch (error) {
      setDropState({
        key,
        status: "error",
        message: error instanceof Error ? error.message : "Upload failed",
      });
      clearDropLater(workspaceId, section);
      return;
    }

    setDropState({
      key,
      status: "done",
      message:
        section === "sessions"
          ? `${list.length} session${list.length === 1 ? "" : "s"} added.`
          : `${list.length} file${list.length === 1 ? "" : "s"} added.`,
    });
    clearDropLater(workspaceId, section);
  }

  return (
    <aside className="scroll-thin overflow-y-auto border-r border-border bg-surface">
      <div className="px-3 pb-1 pt-3">
        <Link href="/" className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/octopus.svg" alt="Stash" className="h-7 w-7" />
          <span className="font-display text-[14px] font-semibold tracking-tight text-foreground">
            stash
          </span>
        </Link>
      </div>

      <nav className="px-2 pt-2 text-[13px]">
        <button
          onClick={onCmdkOpen}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-muted hover:bg-raised"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          Search
          <span className="ml-auto rounded bg-base px-1 py-0 font-mono text-[10px] text-muted ring-1 ring-border">
            ⌘K
          </span>
        </button>
        <NavRow
          href="/discover"
          icon={<DiscoverIcon />}
          label="Discover"
          active={pathname.startsWith("/discover")}
        />
        <NavRow
          href="/activity"
          icon={<ActivityIcon />}
          label="Activity"
          active={pathname.startsWith("/activity")}
        />
      </nav>

      {shared.length > 0 && (
        <>
          <div className="mt-4 flex items-center justify-between px-3 pb-1">
            <span className="text-[11px] font-semibold tracking-wide text-muted">
              SHARED WORKSPACES
            </span>
          </div>
          <nav className="px-1 text-[13.5px]">
            {shared.map((s) => (
              <WorkspaceTree
                key={s.id}
                workspace={{ ...s, shared: true }}
                spine={spines[s.id] ?? null}
                open={isWorkspaceOpen(s.id)}
                onOpenChange={(open) => handleWorkspaceOpenChange(s.id, open)}
                openSections={getOpenSections(s.id)}
                onSectionOpenChange={(section, open) =>
                  handleSectionOpenChange(s.id, section, open)
                }
                pathname={pathname}
                dropState={dropState}
                onDropFiles={handleDropFiles}
                onDropHover={handleDropHover}
              />
            ))}
          </nav>
        </>
      )}

      <div className="mt-4 flex items-center justify-between px-3 pb-1">
        <span className="text-[11px] font-semibold tracking-wide text-muted">MY WORKSPACES</span>
        <details className="relative">
          <summary
            className="flex h-5 w-5 cursor-pointer list-none items-center justify-center rounded text-muted hover:bg-raised hover:text-foreground [&::-webkit-details-marker]:hidden"
            title="Workspace menu"
            aria-label="Workspace menu"
          >
            ⋯
          </summary>
          <div className="absolute right-0 top-full z-20 mt-1 w-40 overflow-hidden rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-lg">
            <Link
              href="/workspaces/new"
              className="block px-3 py-1.5 text-foreground hover:bg-raised"
            >
              + New workspace
            </Link>
          </div>
        </details>
      </div>
      <nav className="px-1 text-[13.5px]">
        {mine.map((s) => (
          <WorkspaceTree
            key={s.id}
            workspace={s}
            spine={spines[s.id] ?? null}
            open={isWorkspaceOpen(s.id)}
            onOpenChange={(open) => handleWorkspaceOpenChange(s.id, open)}
            openSections={getOpenSections(s.id)}
            onSectionOpenChange={(section, open) =>
              handleSectionOpenChange(s.id, section, open)
            }
            pathname={pathname}
            dropState={dropState}
            onDropFiles={handleDropFiles}
            onDropHover={handleDropHover}
          />
        ))}
        {mine.length === 0 && (
          <div className="px-3 py-1.5 text-[12px] italic text-muted">
            No workspaces yet.
          </div>
        )}
      </nav>

      <div className="mt-6 border-t border-border px-2 py-2">
        <NavRow href="/docs" icon={<HelpIcon />} label="Docs" active={pathname.startsWith("/docs")} />
        <NavRow href="/settings" icon={<SettingsIcon />} label="Settings" active={pathname.startsWith("/settings")} />
      </div>
    </aside>
  );
}
