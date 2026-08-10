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
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { create } from "zustand";
import { Skeleton } from "@/components/ui/skeleton";
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
    </>
  );
  const cls = cn(
    "group flex w-full items-center gap-1.5 rounded-md py-[3px] pr-1.5",
    active ? "bg-brand-500/10" : "hover:bg-raised",
  );
  if (href) {
    return (
      // Navigating into a closed folder also opens it, like VS Code.
      <Link href={href} style={pad} className={cls} onClick={() => { if (isDir && !open) onToggle?.(); }}>
        {inner}
      </Link>
    );
  }
  if (isDir) {
    return (
      <button type="button" onClick={onToggle} style={pad} className={cls}>
        {inner}
      </button>
    );
  }
  return <div style={pad} className={cn(cls, "hover:bg-transparent")}>{inner}</div>;
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
}: {
  nodes: VNode[];
  depth: number;
  parentKey: string;
  apiHidden?: number;
  moreHref?: string;
  pathname: string;
  showAll: Set<string>;
  onRevealAll: (key: string) => void;
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
            />
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
}: {
  mount: Mount;
  pathname: string;
  showAll: Set<string>;
  onRevealAll: (key: string) => void;
}) {
  const collapsedMounts = useVfsTreeStore((s) => s.collapsedMounts);
  const toggleMount = useVfsTreeStore((s) => s.toggleMount);
  const open = !collapsedMounts.has(mount.path);
  // In the lens /files is where you already are; docked, its row is the way
  // back to the full-screen view.
  const href = mount.path === "/files" ? "/files" : mount.href;
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
      />
      {open && (
        <>
          {mount.nodes.length === 0 && !mount.footer ? (
            <div style={pad} className="py-1 pl-5 font-mono text-[11.5px] italic text-muted-foreground">
              {mount.emptyLabel}
            </div>
          ) : (
            <Nodes
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

export default function VfsTree() {
  const pathname = usePathname();
  const { mounts, coreLoaded, coreError, sourcesPending, sourcesError } = useVfsMounts();
  const reveal = useVfsTreeStore((s) => s.reveal);
  const [showAll, setShowAll] = useState<Set<string>>(new Set());

  // Whatever the workbench has open gets its ancestor chain expanded, so the
  // highlight is always on screen — including right after the lens docks here.
  useEffect(() => {
    for (const mount of mounts) {
      const trail = ancestorsOf(mount.nodes, pathname, []);
      if (trail) {
        reveal(mount.path, trail);
        return;
      }
    }
  }, [pathname, mounts, reveal]);

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
