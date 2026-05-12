"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  type FolderContents,
  type StashSpine,
  type WikiFile,
} from "../lib/api";
import {
  getCachedFolderContents,
  getCachedStashSpine,
  getCachedWorkspaces,
  readCachedFolderContents,
  readCachedSpines,
  readCachedWorkspaces,
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
  WikiIcon,
} from "./StashIcons";

interface AppSidebarProps {
  user?: User;
  onLogout?: () => void;
  cmdkOpen?: boolean;
  onCmdkOpen?: () => void;
}

interface StashNode extends Workspace {
  shared?: boolean;
}

type SidebarSection = "sessions" | "wiki";

const OPEN_STASHES_KEY = "stash_sidebar_open_stashes";
const OPEN_SECTIONS_KEY = "stash_sidebar_open_sections";

function readOpenMap(key: string): Record<string, boolean> {
  if (typeof window === "undefined") return {};

  const raw = window.localStorage.getItem(key);
  if (!raw) return {};

  return Object.fromEntries(
    raw
      .split("\n")
      .filter(Boolean)
      .map((id) => [id, true])
  );
}

function writeOpenMap(key: string, value: Record<string, boolean>) {
  if (typeof window === "undefined") return;

  const openIds = Object.keys(value).filter((id) => value[id]);
  window.localStorage.setItem(key, openIds.join("\n"));
}

function sectionKey(stashId: string, section: SidebarSection): string {
  return `${stashId}:${section}`;
}

function Chevron() {
  return (
    <svg
      className="chev h-3 w-3 text-muted"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
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

function StashTree({
  stash,
  spine,
  open,
  onOpenChange,
  openSections,
  onSectionOpenChange,
  pathname,
}: {
  stash: StashNode;
  spine: StashSpine | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  openSections: Record<SidebarSection, boolean>;
  onSectionOpenChange: (section: SidebarSection, open: boolean) => void;
  pathname: string;
}) {
  const isActive = pathname === `/stashes/${stash.id}`;

  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="group/stash"
    >
      <summary className="page-row flex items-center gap-1 rounded-md px-2 py-1 text-[13px] hover:bg-raised">
        <Chevron />
        <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
          <StashIcon />
        </span>
        <Link
          href={`/stashes/${stash.id}`}
          className={
            "flex-1 truncate font-medium " +
            (isActive ? "text-[var(--color-brand-800)]" : "text-foreground")
          }
        >
          {stash.name}
        </Link>
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        <details
          open={openSections.sessions}
          onToggle={(e) => onSectionOpenChange("sessions", e.currentTarget.open)}
          className="text-[13px]"
        >
          <summary className="page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised">
            <Chevron />
            <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
              <SessionsIcon />
            </span>
            <span className="flex-1 truncate font-medium text-foreground">Sessions</span>
            <span className="text-[10.5px] text-muted">{spine?.sessions.length ?? 0}</span>
          </summary>
          <div className="ml-3 space-y-0.5 border-l border-border pl-2">
            {spine?.sessions.slice(0, 8).map((s) => (
              <NavRow
                key={s.session_id}
                href={`/stashes/${stash.id}/sessions/${encodeURIComponent(s.session_id)}`}
                icon={<span className="text-muted">#</span>}
                label={s.session_id.length > 22 ? s.session_id.slice(0, 22) + "…" : s.session_id}
              />
            ))}
            {(!spine || spine.sessions.length === 0) && (
              <div className="px-2 py-1 text-[11px] italic text-muted">empty</div>
            )}
          </div>
        </details>

        <WikiBlock
          stash={stash}
          spine={spine}
          open={openSections.wiki}
          onOpenChange={(nextOpen) => onSectionOpenChange("wiki", nextOpen)}
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
  stashId,
  file,
}: {
  stashId: string;
  file: Pick<WikiFile, "id" | "name" | "content_type" | "linked_table_id">;
}) {
  const isCsvLinked =
    file.content_type?.includes("csv") && file.linked_table_id;
  const href = isCsvLinked
    ? `/tables/${file.linked_table_id}?workspaceId=${stashId}`
    : `/stashes/${stashId}/f/${file.id}`;
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

function FolderTreeNode({
  stashId,
  folderId,
  name,
}: {
  stashId: string;
  folderId: string;
  name: string;
}) {
  const cachedContents = readCachedFolderContents(folderId);
  const [contents, setContents] = useState<FolderContents | null>(cachedContents);
  const [loaded, setLoaded] = useState(!!cachedContents);
  return (
    <details
      className="text-[12.5px]"
      onToggle={(e) => {
        if ((e.target as HTMLDetailsElement).open && !loaded) {
          setLoaded(true);
          getCachedFolderContents(stashId, folderId)
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
      }}
    >
      <summary className="page-row flex items-center gap-1 rounded-md px-2 py-0.5 hover:bg-raised">
        <Chevron />
        <span className="flex h-4 w-4 items-center justify-center text-muted">
          <FolderIcon />
        </span>
        <Link
          href={`/stashes/${stashId}/folders/${folderId}`}
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
            stashId={stashId}
            folderId={sub.id}
            name={sub.name}
          />
        ))}
        {contents?.pages.map((p) => (
          <NavRow
            key={p.id}
            href={`/stashes/${stashId}/p/${p.id}`}
            icon={<PageIcon className="text-muted" />}
            label={p.name}
          />
        ))}
        {contents?.files.map((f) => (
          <FileNavRow key={f.id} stashId={stashId} file={f} />
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

function WikiBlock({
  stash,
  spine,
  open,
  onOpenChange,
}: {
  stash: StashNode;
  spine: StashSpine | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const folders = spine?.wiki.folders ?? [];
  const pages = spine?.wiki.pages ?? [];
  const files = spine?.wiki.files ?? [];
  const rootFolders = folders.filter((f) => !f.parent_folder_id);
  const rootPages = pages.filter((p) => !p.folder_id);
  const rootFiles = files.filter((f) => !f.folder_id);
  const total = folders.length + pages.length + files.length;
  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="text-[13px]"
    >
      <summary className="page-row flex items-center gap-1 rounded-md px-2 py-1 hover:bg-raised">
        <Chevron />
        <span className="flex h-4 w-4 items-center justify-center text-[14px] text-muted">
          <WikiIcon />
        </span>
        <span className="flex-1 truncate font-medium text-foreground">Wiki</span>
        <span className="text-[10.5px] text-muted">{total}</span>
      </summary>
      <div className="ml-3 space-y-0.5 border-l border-border pl-2">
        {rootFolders.map((f) => (
          <FolderTreeNode
            key={f.id}
            stashId={stash.id}
            folderId={f.id}
            name={f.name}
          />
        ))}
        {rootPages.slice(0, 10).map((p) => (
          <NavRow
            key={p.id}
            href={`/stashes/${stash.id}/p/${p.id}`}
            icon={<PageIcon className="text-muted" />}
            label={p.name}
          />
        ))}
        {rootFiles.slice(0, 12).map((f) => (
          <FileNavRow key={f.id} stashId={stash.id} file={f} />
        ))}
        {!spine || total === 0 ? (
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
    /^\/stashes\/([^/]+)\/(sessions|folders|p|f|skills)(?:\/|$)/
  );
  const activeTreeStashId = activeTreeMatch?.[1] ?? null;
  const activeTreeSection: SidebarSection | null =
    activeTreeMatch?.[2] === "sessions"
      ? "sessions"
      : activeTreeMatch
        ? "wiki"
        : null;
  const [mine, setMine] = useState<Workspace[]>(cachedWorkspaces?.mine ?? []);
  const [shared, setShared] = useState<Workspace[]>(cachedWorkspaces?.shared ?? []);
  const [openStashes, setOpenStashes] = useState<Record<string, boolean>>(() =>
    readOpenMap(OPEN_STASHES_KEY)
  );
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() =>
    readOpenMap(OPEN_SECTIONS_KEY)
  );
  const [spines, setSpines] = useState<Record<string, StashSpine>>(() =>
    readCachedSpines()
  );

  useEffect(() => {
    if (!userId) return;

    getCachedWorkspaces(userId)
      .then((r) => {
        setMine(r.mine);
        setShared(r.shared);
      })
      .catch(() => {});
  }, [userId]);

  const setOpenStash = useCallback((stashId: string, open: boolean) => {
    setOpenStashes((current) => {
      const next = { ...current };
      if (open) {
        next[stashId] = true;
      } else {
        delete next[stashId];
      }
      writeOpenMap(OPEN_STASHES_KEY, next);
      return next;
    });
  }, []);

  const setOpenSection = useCallback((
    stashId: string,
    section: SidebarSection,
    open: boolean
  ) => {
    setOpenSections((current) => {
      const next = { ...current };
      const key = sectionKey(stashId, section);
      if (open) {
        next[key] = true;
      } else {
        delete next[key];
      }
      writeOpenMap(OPEN_SECTIONS_KEY, next);
      return next;
    });
  }, []);

  useEffect(() => {
    const openIds = Object.keys(openStashes).filter((stashId) => openStashes[stashId]);
    if (activeTreeStashId) openIds.push(activeTreeStashId);

    Array.from(new Set(openIds))
      .filter((stashId) => !spines[stashId])
      .forEach((stashId) => {
        getCachedStashSpine(stashId)
          .then((sp) => setSpines((all) => ({ ...all, [stashId]: sp })))
          .catch(() => {});
      });
  }, [activeTreeStashId, openStashes, spines]);

  function getOpenSections(stashId: string): Record<SidebarSection, boolean> {
    return {
      sessions:
        !!openSections[sectionKey(stashId, "sessions")] ||
        (activeTreeStashId === stashId && activeTreeSection === "sessions"),
      wiki:
        !!openSections[sectionKey(stashId, "wiki")] ||
        (activeTreeStashId === stashId && activeTreeSection === "wiki"),
    };
  }

  function isStashOpen(stashId: string): boolean {
    return !!openStashes[stashId] || activeTreeStashId === stashId;
  }

  function handleStashOpenChange(stashId: string, open: boolean) {
    if (open && activeTreeStashId === stashId && !openStashes[stashId]) return;
    setOpenStash(stashId, open);
  }

  function handleSectionOpenChange(
    stashId: string,
    section: SidebarSection,
    open: boolean
  ) {
    const isRouteOpen =
      activeTreeStashId === stashId &&
      activeTreeSection === section &&
      !openSections[sectionKey(stashId, section)];
    if (open && isRouteOpen) return;
    setOpenSection(stashId, section, open);
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
          active={pathname.startsWith("/activity") || pathname.includes("/activity")}
        />
      </nav>

      {shared.length > 0 && (
        <>
          <div className="mt-4 flex items-center justify-between px-3 pb-1">
            <span className="text-[11px] font-semibold tracking-wide text-muted">
              SHARED WITH ME
            </span>
          </div>
          <nav className="px-1 text-[13.5px]">
            {shared.map((s) => (
              <StashTree
                key={s.id}
                stash={{ ...s, shared: true }}
                spine={spines[s.id] ?? null}
                open={isStashOpen(s.id)}
                onOpenChange={(open) => handleStashOpenChange(s.id, open)}
                openSections={getOpenSections(s.id)}
                onSectionOpenChange={(section, open) =>
                  handleSectionOpenChange(s.id, section, open)
                }
                pathname={pathname}
              />
            ))}
          </nav>
        </>
      )}

      <div className="mt-4 flex items-center justify-between px-3 pb-1">
        <span className="text-[11px] font-semibold tracking-wide text-muted">MY STASHES</span>
        <Link
          href="/stashes/new"
          className="rounded p-0.5 text-muted hover:bg-base hover:text-foreground"
          title="New stash"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </Link>
      </div>
      <nav className="px-1 text-[13.5px]">
        {mine.map((s) => (
          <StashTree
            key={s.id}
            stash={s}
            spine={spines[s.id] ?? null}
            open={isStashOpen(s.id)}
            onOpenChange={(open) => handleStashOpenChange(s.id, open)}
            openSections={getOpenSections(s.id)}
            onSectionOpenChange={(section, open) =>
              handleSectionOpenChange(s.id, section, open)
            }
            pathname={pathname}
          />
        ))}
        {mine.length === 0 && (
          <div className="px-3 py-1.5 text-[12px] italic text-muted">
            No stashes yet —{" "}
            <Link href="/stashes/new" className="text-[var(--color-brand-700)] underline">
              create one
            </Link>
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
