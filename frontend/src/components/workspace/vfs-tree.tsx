"use client";

// The docked VFS — the same mounts the full-screen /files lens shows, drawn
// as a persistent VS Code-style tree: the whole filesystem stays visible,
// folders pin open on click, and whatever the workbench has open is
// highlighted with its ancestors revealed. It shares the lens's paper
// background and icons on purpose: clicking an item in the lens should read
// as that view snapping to the left, not as arriving somewhere new.

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { ArrowUpRight, ChevronRight, FolderPlus } from "lucide-react";
import { create } from "zustand";
import { Skeleton } from "@/components/ui/skeleton";
import { createFolder } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import type { VNode } from "@/components/content/files-overview/build";
import { NodeIcon, useVfsMounts, type Mount } from "@/components/content/files-overview/useVfsMounts";

const SHOW_PER_DIR = 10;
const INDENT_PX = 14;

// Expansion lives in a store, not component state: the tree unmounts whenever
// the user visits a full-screen surface and must come back looking the same.
// Mounts are open unless collapsed; inner folders are closed unless expanded.
interface VfsTreeState {
  expanded: Set<string>;
  collapsedMounts: Set<string>;
  toggleNode: (key: string) => void;
  toggleMount: (path: string) => void;
  reveal: (mountPath: string, nodeKeys: string[]) => void;
}

const useVfsTreeStore = create<VfsTreeState>((set) => ({
  expanded: new Set<string>(),
  collapsedMounts: new Set<string>(),
  toggleNode: (key) =>
    set((s) => {
      const expanded = new Set(s.expanded);
      if (expanded.has(key)) expanded.delete(key);
      else expanded.add(key);
      return { expanded };
    }),
  toggleMount: (path) =>
    set((s) => {
      const collapsedMounts = new Set(s.collapsedMounts);
      if (collapsedMounts.has(path)) collapsedMounts.delete(path);
      else collapsedMounts.add(path);
      return { collapsedMounts };
    }),
  reveal: (mountPath, nodeKeys) =>
    set((s) => {
      const expanded = new Set(s.expanded);
      nodeKeys.forEach((k) => expanded.add(k));
      const collapsedMounts = new Set(s.collapsedMounts);
      collapsedMounts.delete(mountPath);
      return { expanded, collapsedMounts };
    }),
}));

function pathOf(href: string | undefined): string | undefined {
  return href?.split("?")[0];
}

/** Keys of every folder above the node whose href matches `pathname`. */
function ancestorsOf(nodes: VNode[], pathname: string, trail: string[]): string[] | null {
  for (const node of nodes) {
    if (pathOf(node.href) === pathname) return trail;
    if (node.children) {
      const found = ancestorsOf(node.children, pathname, [...trail, node.key]);
      if (found) return found;
    }
  }
  return null;
}

// Each directory renders only its first SHOW_PER_DIR children, so an item can
// be revealed — ancestors expanded, row marked active — and still not be on
// screen because it fell past the "+N more" cut. This is the key of the
// directory holding the match, whose list then has to be shown in full.
function truncatedParentOf(
  nodes: VNode[],
  pathname: string,
  parentKey: string,
): string | null {
  const index = nodes.findIndex((node) => pathOf(node.href) === pathname);
  if (index >= SHOW_PER_DIR) return parentKey;
  if (index !== -1) return null;
  for (const node of nodes) {
    if (!node.children) continue;
    const found = truncatedParentOf(node.children, pathname, node.key);
    if (found) return found;
  }
  return null;
}

function Row({
  depth,
  icon,
  label,
  annotation,
  isDir,
  isEmptyDir,
  open,
  active,
  href,
  mono,
  onToggle,
  onAddFolder,
}: {
  depth: number;
  icon: React.ReactNode;
  label: string;
  annotation?: string;
  isDir: boolean;
  isEmptyDir?: boolean;
  open?: boolean;
  active?: boolean;
  href?: string;
  mono?: boolean;
  onToggle?: () => void;
  /** Present on rows that can hold folders; shown on hover. */
  onAddFolder?: () => void;
}) {
  const pad = { paddingLeft: 6 + depth * INDENT_PX };
  const inner = (
    <>
      {isDir ? (
        // Inside a navigating row the chevron keeps toggle duty: label clicks
        // follow the href, chevron clicks expand/collapse.
        <span
          role="button"
          aria-label={open ? "collapse" : "expand"}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onToggle?.();
          }}
          className="flex h-4 w-4 shrink-0 items-center justify-center"
        >
          <ChevronRight
            className={cn("h-3 w-3 text-muted-foreground transition-transform", open && "rotate-90")}
          />
        </span>
      ) : (
        <span className="w-4 shrink-0" />
      )}
      <span className="flex w-[15px] shrink-0 items-center justify-center [&_svg]:h-[15px] [&_svg]:w-[15px] [&_img]:h-[15px] [&_img]:w-[15px]">
        {icon}
      </span>
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-left text-[13px]",
          mono && "font-mono",
          isEmptyDir ? "text-muted-foreground" : active ? "text-brand-700" : "text-foreground",
        )}
      >
        {label}
        {(isDir || isEmptyDir) && !mono && <span className="text-muted-foreground">/</span>}
      </span>
      {annotation && (
        <span className="shrink-0 pl-1.5 font-mono text-[10.5px] text-muted-foreground">{annotation}</span>
      )}
      {onAddFolder && (
        <span
          role="button"
          aria-label="New folder"
          title="New folder"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onAddFolder();
          }}
          className="ml-0.5 hidden shrink-0 rounded p-0.5 text-muted-foreground hover:bg-raised hover:text-brand-700 group-hover:block"
        >
          <FolderPlus className="h-3.5 w-3.5" />
        </span>
      )}
    </>
  );
  const cls = cn(
    "group flex w-full items-center gap-1.5 rounded-md py-[3px] pr-1.5",
    active ? "bg-brand-500/10" : "hover:bg-raised",
  );
  if (href) {
    return (
      // Navigating into a closed folder also opens it, like VS Code.
      <Link
        href={href}
        style={pad}
        className={cls}
        data-vfs-active={active || undefined}
        onClick={() => { if (isDir && !open) onToggle?.(); }}
      >
        {inner}
      </Link>
    );
  }
  if (isDir) {
    return (
      <button type="button" onClick={onToggle} style={pad} className={cls} data-vfs-active={active || undefined}>
        {inner}
      </button>
    );
  }
  return <div style={pad} className={cn(cls, "hover:bg-transparent")}>{inner}</div>;
}

/** The row that appears when you click +: type a name, Enter creates it,
 *  Escape gives up. No dialog for something this small. */
function NewFolderRow({
  depth,
  parentId,
  onDone,
}: {
  depth: number;
  parentId: string | null;
  onDone: (created: boolean) => void;
}) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  async function create() {
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      await createFolder(trimmed, parentId);
      onDone(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't create that folder");
      setSaving(false);
    }
  }

  return (
    <div
      style={{ paddingLeft: 6 + depth * INDENT_PX }}
      className="flex w-full items-center gap-1.5 py-[3px] pr-1.5"
    >
      <span className="w-4 shrink-0" />
      <span className="flex w-[15px] shrink-0 items-center justify-center text-brand-600">
        <FolderPlus className="h-3.5 w-3.5" />
      </span>
      <input
        autoFocus
        value={name}
        disabled={saving}
        onChange={(e) => setName(e.target.value)}
        onBlur={() => onDone(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void create();
          if (e.key === "Escape") onDone(false);
        }}
        placeholder="folder name"
        className="min-w-0 flex-1 rounded-sm bg-transparent text-[13px] text-foreground outline-none ring-1 ring-brand-400 placeholder:text-muted-foreground"
      />
    </div>
  );
}

function Nodes({
  nodes,
  depth,
  parentKey,
  apiHidden,
  moreHref,
  pathname,
  showAll,
  onRevealAll,
  addingIn,
  onAddFolder,
  onAddDone,
  foldable,
}: {
  nodes: VNode[];
  depth: number;
  parentKey: string;
  apiHidden?: number;
  moreHref?: string;
  pathname: string;
  showAll: Set<string>;
  onRevealAll: (key: string) => void;
  addingIn: string | null;
  onAddFolder: (parentId: string | null) => void;
  onAddDone: (created: boolean) => void;
  foldable: boolean;
}) {
  const expanded = useVfsTreeStore((s) => s.expanded);
  const toggleNode = useVfsTreeStore((s) => s.toggleNode);
  const visible = showAll.has(parentKey) ? nodes : nodes.slice(0, SHOW_PER_DIR);
  const hidden = nodes.length - visible.length;
  const pad = { paddingLeft: 6 + depth * INDENT_PX };

  return (
    <>
      {visible.map((node) => {
        const isDir = !!node.children && (node.children.length > 0 || !!node.hiddenCount);
        const isEmptyDir = !!node.children && !isDir;
        const open = isDir && expanded.has(node.key);
        return (
          <div key={node.key}>
            <Row
              depth={depth}
              icon={<NodeIcon node={node} open={open} />}
              label={node.name}
              annotation={node.annotation}
              isDir={isDir}
              isEmptyDir={isEmptyDir}
              open={open}
              active={pathOf(node.href) === pathname}
              href={node.href}
              onToggle={() => toggleNode(node.key)}
              onAddFolder={
                foldable && node.kind === "folder" ? () => onAddFolder(node.key) : undefined
              }
            />
            {addingIn === node.key && (
              <NewFolderRow depth={depth + 1} parentId={node.key} onDone={onAddDone} />
            )}
            {open && (
              <Nodes
                nodes={node.children!}
                depth={depth + 1}
                parentKey={node.key}
                apiHidden={node.hiddenCount}
                moreHref={node.moreHref ?? moreHref}
                pathname={pathname}
                showAll={showAll}
                onRevealAll={onRevealAll}
                addingIn={addingIn}
                onAddFolder={onAddFolder}
                onAddDone={onAddDone}
                foldable={foldable}
              />
            )}
          </div>
        );
      })}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => onRevealAll(parentKey)}
          style={pad}
          className="flex w-full items-center gap-1 rounded-md py-1 pl-5 text-left font-mono text-[11.5px] text-dim hover:bg-raised hover:text-brand-700"
        >
          … +{hidden} more
        </button>
      )}
      {apiHidden ? (
        moreHref ? (
          <Link
            href={moreHref}
            style={pad}
            className="flex w-full items-center gap-1 rounded-md py-1 pl-5 font-mono text-[11.5px] text-dim hover:bg-raised hover:text-brand-700"
          >
            … {apiHidden} more synced <ArrowUpRight className="h-3 w-3" />
          </Link>
        ) : (
          <div style={pad} className="flex w-full items-center gap-1 py-1 pl-5 font-mono text-[11.5px] text-muted-foreground">
            … {apiHidden} more synced
          </div>
        )
      ) : null}
    </>
  );
}

function MountBlock({
  mount,
  pathname,
  showAll,
  onRevealAll,
  addingIn,
  onAddFolder,
  onAddDone,
}: {
  mount: Mount;
  pathname: string;
  showAll: Set<string>;
  onRevealAll: (key: string) => void;
  addingIn: string | null;
  onAddFolder: (parentId: string | null) => void;
  onAddDone: (created: boolean) => void;
}) {
  const collapsedMounts = useVfsTreeStore((s) => s.collapsedMounts);
  const toggleMount = useVfsTreeStore((s) => s.toggleMount);
  const open = !collapsedMounts.has(mount.path);
  // In the lens /files is where you already are; docked, its row is the way
  // back to the full-screen view.
  const href = mount.path === "/files" ? "/files" : mount.href;
  const foldable = mount.path === "/files";
  const pad = { paddingLeft: 6 + INDENT_PX };

  return (
    <div className="pb-1">
      <Row
        depth={0}
        icon={mount.icon}
        label={mount.path}
        isDir
        open={open}
        active={pathOf(href) === pathname}
        href={href}
        mono
        onToggle={() => toggleMount(mount.path)}
        onAddFolder={foldable ? () => onAddFolder(null) : undefined}
      />
      {foldable && addingIn === ROOT_KEY && (
        <NewFolderRow depth={1} parentId={null} onDone={onAddDone} />
      )}
      {open && (
        <>
          {mount.nodes.length === 0 && !mount.footer ? (
            <div style={pad} className="py-1 pl-5 font-mono text-[11.5px] italic text-muted-foreground">
              {mount.emptyLabel}
            </div>
          ) : (
            <Nodes
              addingIn={addingIn}
              onAddFolder={onAddFolder}
              onAddDone={onAddDone}
              foldable={foldable}
              nodes={mount.nodes}
              depth={1}
              parentKey={mount.path}
              apiHidden={mount.apiHidden}
              moreHref={mount.moreHref}
              pathname={pathname}
              showAll={showAll}
              onRevealAll={onRevealAll}
            />
          )}
          {mount.footer && (
            <Link
              href={mount.footer.href}
              style={pad}
              className="group flex w-full items-center gap-1 rounded-md py-1 pl-5 font-mono text-[11.5px] text-dim hover:bg-raised hover:text-brand-700"
            >
              {mount.footer.label}
              <ArrowUpRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
            </Link>
          )}
        </>
      )}
    </div>
  );
}

// The sentinel for "creating at the top level of /files", where there is no
// parent folder id to key off.
const ROOT_KEY = "__root__";

export default function VfsTree() {
  const pathname = usePathname();
  const { mounts, coreLoaded, coreError, sourcesPending, sourcesError, reload } = useVfsMounts();
  const [addingIn, setAddingIn] = useState<string | null>(null);
  const reveal = useVfsTreeStore((s) => s.reveal);
  const expanded = useVfsTreeStore((s) => s.expanded);
  const [showAll, setShowAll] = useState<Set<string>>(new Set());

  // Whatever the workbench has open gets its ancestor chain expanded, so the
  // highlight is always on screen — including right after the lens docks here.
  useEffect(() => {
    for (const mount of mounts) {
      const trail = ancestorsOf(mount.nodes, pathname, []);
      if (!trail) continue;
      reveal(mount.path, trail);
      const truncated = truncatedParentOf(mount.nodes, pathname, mount.path);
      if (truncated) setShowAll((prev) => new Set(prev).add(truncated));
      return;
    }
  }, [pathname, mounts, reveal]);

  // Orientation needs the highlight on screen, and the row only exists once
  // its ancestors are expanded and its directory un-truncated — so this runs
  // after those, not with them. "nearest" leaves an already-visible row alone.
  useEffect(() => {
    document.querySelector("[data-vfs-active]")?.scrollIntoView({ block: "nearest" });
  }, [pathname, expanded, showAll]);

  if (coreError) {
    return <div className="p-3 font-mono text-[12px] text-error">✗ couldn&apos;t read the stash: {coreError}</div>;
  }

  return (
    <div className="h-full overflow-y-auto bg-base px-1.5 py-2">
      {!coreLoaded && (
        <div className="space-y-3 p-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-4" style={{ width: `${90 + (i % 3) * 30}px` }} />
          ))}
        </div>
      )}
      {mounts.map((mount) => (
        <MountBlock
          key={mount.path}
          mount={mount}
          pathname={pathname}
          showAll={showAll}
          onRevealAll={(key) => setShowAll((prev) => new Set(prev).add(key))}
          addingIn={addingIn}
          onAddFolder={(parentId) => {
            // Creating inside a folder only makes sense with it open.
            if (parentId) reveal("/files", [parentId]);
            setAddingIn(parentId ?? ROOT_KEY);
          }}
          onAddDone={(created) => {
            setAddingIn(null);
            if (created) reload();
          }}
        />
      ))}
      {coreLoaded && sourcesPending && (
        <div className="space-y-2 p-2">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-4 w-20" />
        </div>
      )}
      {sourcesError && <div className="p-2 font-mono text-[12px] text-error">✗ /sources: {sourcesError}</div>}
    </div>
  );
}
