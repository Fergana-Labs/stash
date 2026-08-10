"use client";

// The /files page: the VFS root as a cursor-driven lens. At rest it is bare
// `ls -1` output — one mount path per line. The mount under the cursor blooms
// open one level, and hovering any folder row expands it in place. Folders
// stay open while the lens is on their mount — collapsing happens only when
// focus moves to another mount — so rows are never yanked out from under a
// traveling cursor. A spring-loaded depth gauge above the tree gives a
// transient overview: sweeping across it opens every mount 1-4 levels in
// real time, and leaving it snaps the tree back flat — a peek, not a mode.

import Link from "next/link";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, Brain, Cable, ChevronRight, FolderTree, GraduationCap, MessagesSquare } from "lucide-react";
import {
  getMemoryFolder,
  getMeOverview,
  getSidebar,
  getSourcesTree,
  listSkills,
  listTables,
  type MeOverview,
  type SourceTreeRoot,
} from "@/lib/api";
import { FileIcon, FolderIcon, PageIcon, TableIcon } from "@/components/SkillIcons";
import { connectorIcon } from "@/components/integrations/connectors";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  buildFilesNodes,
  buildSessionNodes,
  buildSkillNodes,
  buildSourceNodes,
  buildTableNodes,
  type VNode,
} from "./build";

const SHOW_PER_DIR = 10;
const RECENT_SESSIONS = 8;
const UNFOCUS_DELAY_MS = 250;

/** Cursor position across the gauge bars → depth floor 0-3. */
function gaugeDepth(e: React.MouseEvent<HTMLDivElement>): number {
  const r = e.currentTarget.getBoundingClientRect();
  if (r.width <= 0) return 0;
  const frac = (e.clientX - r.left) / r.width;
  return Math.max(0, Math.min(3, Math.floor(frac * 4)));
}

interface Mount {
  path: string;
  icon: ReactNode;
  nodes: VNode[];
  href?: string;
  /** Rows the API cut off before we ever saw them (sources per-dir cap). */
  apiHidden?: number;
  /** Where "+N more" rows we can't expand locally should take the user. */
  moreHref?: string;
  footer?: { label: string; href: string };
  emptyLabel: string;
}

interface CoreData {
  filesNodes: VNode[];
  memoryFolderId: string;
  memoryNodes: VNode[];
  sessionNodes: VNode[];
  skillNodes: VNode[];
  tableNodes: VNode[];
  vitals: MeOverview;
}

export default function FilesOverview() {
  const [core, setCore] = useState<CoreData | null>(null);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceTreeRoot[] | null>(null);
  const [sourcesError, setSourcesError] = useState<string | null>(null);

  // The lens: which mount is bloomed open, and which of its folders the
  // cursor has opened. Hover opens; a chevron click closes; changing mounts
  // resets everything.
  const [focus, setFocus] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState<Set<string>>(new Set());
  // The gauge's global floor while the cursor sweeps it: 0 = bare list,
  // 1 = every mount bloomed one level, ... Springs back on leave — to 0, or
  // to the depth the user pinned by clicking the gauge.
  const [globalDepth, setGlobalDepth] = useState(0);
  const [pinnedDepth, setPinnedDepth] = useState<number | null>(null);

  const unfocusTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getSidebar(), listTables(), listSkills(), getMeOverview(), getMemoryFolder()])
      .then(([sidebar, tables, skills, vitals, memoryFolder]) => {
        if (cancelled) return;
        const { files, memory } = buildFilesNodes(sidebar.files, memoryFolder.id);
        setCore({
          filesNodes: files,
          memoryFolderId: memoryFolder.id,
          memoryNodes: memory,
          sessionNodes: buildSessionNodes(sidebar.sessions.slice(0, RECENT_SESSIONS)),
          skillNodes: buildSkillNodes(skills),
          tableNodes: buildTableNodes(tables.tables),
          vitals,
        });
      })
      .catch((e) => { if (!cancelled) setCoreError(e instanceof Error ? e.message : String(e)); });
    // The sources tree walks every connected source, so it loads on its own
    // clock — the native mounts render without waiting for it.
    getSourcesTree()
      .then((s) => { if (!cancelled) setSources(s); })
      .catch((e) => { if (!cancelled) setSourcesError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, []);

  const mounts = useMemo<Mount[]>(() => {
    if (!core) return [];
    const native: Mount[] = [
      {
        path: "/files",
        icon: <FolderTree className="h-4 w-4 text-chart-4" />,
        nodes: core.filesNodes,
        emptyLabel: "empty",
      },
      {
        path: "/sessions",
        icon: <MessagesSquare className="h-4 w-4 text-chart-1" />,
        nodes: core.sessionNodes,
        href: "/sessions",
        footer:
          core.vitals.sessions > core.sessionNodes.length
            ? { label: `all ${core.vitals.sessions} sessions`, href: "/sessions" }
            : undefined,
        emptyLabel: "no sessions yet",
      },
      {
        path: "/memory",
        icon: <Brain className="h-4 w-4 text-chart-2" />,
        nodes: core.memoryNodes,
        href: `/folders/${core.memoryFolderId}`,
        emptyLabel: "nothing remembered yet",
      },
      {
        path: "/skills",
        icon: <GraduationCap className="h-4 w-4 text-chart-3" />,
        nodes: core.skillNodes,
        href: "/skills",
        emptyLabel: "no skills yet",
      },
      {
        path: "/tables",
        icon: <span className="text-chart-5"><TableIcon /></span>,
        nodes: core.tableNodes,
        emptyLabel: "no tables yet",
      },
    ];
    if (sources === null) return native;
    // One faithful /sources mount, exactly like the VFS: providers are
    // directories inside it, wearing their brand marks.
    const providerNodes = sources
      .map<VNode>((root) => {
        const provider = root.provider ?? root.source;
        const { nodes, hiddenCount } = buildSourceNodes(root.tree, `/sources/${provider}`);
        return {
          key: `/sources/${provider}`,
          kind: "folder",
          name: provider,
          icon: connectorIcon(provider),
          href: `/integrations/${provider}`,
          children: nodes,
          hiddenCount: hiddenCount || undefined,
          moreHref: `/integrations/${provider}`,
        };
      })
      // Providers with synced content are what the VFS really materializes,
      // so they sort ahead of the empty (greyed) ones; alphabetical within
      // each group.
      .sort((a, b) => {
        const aEmpty = a.children!.length === 0 && !a.hiddenCount ? 1 : 0;
        const bEmpty = b.children!.length === 0 && !b.hiddenCount ? 1 : 0;
        return aEmpty - bEmpty || a.name.localeCompare(b.name);
      });
    return [
      ...native,
      {
        path: "/sources",
        icon: <Cable className="h-4 w-4 text-chart-1" />,
        nodes: providerNodes,
        footer:
          providerNodes.length === 0
            ? { label: "connect a source", href: "/settings/integrations" }
            : undefined,
        emptyLabel: "no sources connected",
      },
    ];
  }, [core, sources]);

  function focusMount(path: string) {
    if (unfocusTimer.current) clearTimeout(unfocusTimer.current);
    unfocusTimer.current = null;
    setFocus((current) => {
      if (current !== path) setOpen(new Set());
      return path;
    });
  }

  function onLensLeave() {
    unfocusTimer.current = setTimeout(() => {
      setFocus(null);
      setOpen(new Set());
      setGlobalDepth(pinnedDepth ?? 0);
    }, UNFOCUS_DELAY_MS);
  }

  function hoverDir(key: string) {
    setOpen((prev) => (prev.has(key) ? prev : new Set(prev).add(key)));
  }

  function toggle(key: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }
  function revealAll(key: string) {
    setShowAll((prev) => new Set(prev).add(key));
  }

  if (coreError) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="font-mono text-[13px] text-error">✗ couldn&apos;t read the stash: {coreError}</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-base">
      <div className="mx-auto max-w-[680px] px-8 pb-16 pt-10" onMouseLeave={onLensLeave}>
        {core && (
          <div className="mb-8 flex items-start justify-between gap-2.5">
            <div>
              <h1 className="text-[26px] font-semibold tracking-tight text-foreground">Virtual Filesystem</h1>
              <p className="mt-1.5 text-[13.5px] text-dim">Browse everything your agents can see through the Stash VFS.</p>
            </div>
            {/* Spring-loaded: depth follows the cursor across the bars and
                snaps back when it leaves — to flat, or to a depth pinned by
                clicking. Peek by default, setting only on purpose. */}
            <div className="ml-auto flex items-center gap-2 self-start pt-2">
            <span className="select-none font-mono text-[11px] text-muted-foreground">depth</span>
            <div
              role="slider"
              aria-label="tree depth"
              aria-valuemin={1}
              aria-valuemax={4}
              aria-valuenow={globalDepth + 1}
              tabIndex={-1}
              onMouseMove={(e) => setGlobalDepth(gaugeDepth(e))}
              onMouseLeave={() => setGlobalDepth(pinnedDepth ?? 0)}
              onClick={(e) => {
                const d = gaugeDepth(e);
                setPinnedDepth((current) => (current === d ? null : d));
                setGlobalDepth(d);
              }}
              className="flex cursor-ew-resize items-end gap-[3px] px-1 py-1"
            >
              {[0, 1, 2, 3].map((d) => (
                <span
                  key={d}
                  style={{ height: 5 + d * 4 }}
                  className={cn(
                    "w-[14px] rounded-[2px] transition-colors duration-100",
                    d <= globalDepth ? "bg-brand-500" : "bg-raised",
                  )}
                />
              ))}
            </div>
            </div>
          </div>
        )}
        {!core && (
          <div className="space-y-3 py-1">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-4" style={{ width: `${90 + (i % 3) * 30}px` }} />
            ))}
          </div>
        )}
        {mounts.map((mount) => (
          <MountBlock
            key={mount.path}
            mount={mount}
            bloomed={focus === mount.path || globalDepth >= 1}
            globalDepth={globalDepth}
            onFocus={() => focusMount(mount.path)}
            openDirs={open}
            onHoverDir={hoverDir}
            onToggle={toggle}
            showAll={showAll}
            onRevealAll={revealAll}
          />
        ))}
        {core && sources === null && !sourcesError && (
          <div className="space-y-3 py-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-24" />
          </div>
        )}
        {sourcesError && (
          <div className="py-1 font-mono text-[13px] text-error">✗ /sources: {sourcesError}</div>
        )}
      </div>
    </div>
  );
}

/** One mount: a bare `ls` row at rest; the tree blooms beneath it while the
 *  lens is on it. The whole block keeps focus, so the cursor can travel into
 *  the subtree without the view changing underneath it. */
function MountBlock({
  mount,
  bloomed,
  globalDepth,
  onFocus,
  openDirs,
  onHoverDir,
  onToggle,
  showAll,
  onRevealAll,
}: {
  mount: Mount;
  bloomed: boolean;
  globalDepth: number;
  onFocus: () => void;
  openDirs: Set<string>;
  onHoverDir: (key: string) => void;
  onToggle: (key: string) => void;
  showAll: Set<string>;
  onRevealAll: (key: string) => void;
}) {
  const name = (
    <span className="flex items-center gap-2">
      <span className="flex w-[15px] items-center justify-center [&_svg]:h-[15px] [&_svg]:w-[15px] [&_img]:h-[15px] [&_img]:w-[15px]">
        {mount.icon}
      </span>
      <span
        className={cn(
          "font-mono text-[13px]",
          mount.nodes.length === 0 ? "text-muted-foreground" : "text-foreground",
          bloomed && "font-semibold",
        )}
      >
        {mount.path}
      </span>
    </span>
  );

  return (
    <div onMouseEnter={onFocus}>
      {mount.href ? (
        <Link href={mount.href} className="inline-flex rounded-md px-1.5 py-[3px] hover:bg-raised">{name}</Link>
      ) : (
        <div className="inline-flex px-1.5 py-[3px]">{name}</div>
      )}
      {bloomed && (
        <div className="pb-2 pl-1.5 animate-in fade-in-0 duration-150">
          {mount.nodes.length === 0 && !mount.footer ? (
            <div className="flex items-center gap-1 px-1.5 py-1 font-mono text-[12px] text-muted-foreground">
              <span className="whitespace-pre text-muted-foreground/40">└─ </span>
              <span className="italic">{mount.emptyLabel}</span>
            </div>
          ) : (
            <TreeRows
              nodes={mount.nodes}
              nodeDepth={0}
              ancestors={[]}
              parentKey={mount.path}
              mount={mount}
              globalDepth={globalDepth}
              apiHidden={mount.apiHidden}
              moreHref={mount.moreHref}
              hasTrailing={!!mount.footer}
              openDirs={openDirs}
              onHoverDir={onHoverDir}
              onToggle={onToggle}
              showAll={showAll}
              onRevealAll={onRevealAll}
            />
          )}
          {mount.footer && (
            <Link
              href={mount.footer.href}
              className="group flex w-full items-center gap-1 rounded-md px-1.5 py-1 text-[12.5px] text-dim hover:bg-raised hover:text-brand-700"
            >
              <span className="whitespace-pre font-mono text-[12px] leading-none text-muted-foreground/40">└─ </span>
              <span className="font-mono">{mount.footer.label}</span>
              <ArrowUpRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

function NodeIcon({ node, open }: { node: VNode; open: boolean }) {
  if (node.icon) {
    return (
      <span className="flex w-[15px] shrink-0 items-center justify-center [&_svg]:h-[15px] [&_svg]:w-[15px] [&_img]:h-[15px] [&_img]:w-[15px]">
        {node.icon}
      </span>
    );
  }
  const cls = cn("shrink-0", open ? "text-brand-600" : "text-muted-foreground");
  if (node.kind === "folder") return <span className={cls}><FolderIcon /></span>;
  if (node.kind === "page") return <span className="shrink-0 text-muted-foreground"><PageIcon /></span>;
  if (node.kind === "table") return <span className="shrink-0 text-muted-foreground"><TableIcon /></span>;
  if (node.kind === "session") return <MessagesSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
  if (node.kind === "skill") return <GraduationCap className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
  return <span className="shrink-0 text-muted-foreground"><FileIcon /></span>;
}

/** One directory level, tree(1)-style: `├─`/`└─` glyphs with `│` continuation
 *  lines inherited from open ancestors. Hovering a directory row opens it in
 *  place (a chevron click closes it again). Long listings stop at
 *  SHOW_PER_DIR rows behind a "+N more" toggle; rows the API itself withheld
 *  get an honest "not shown" row instead. */
function TreeRows({
  nodes,
  nodeDepth,
  ancestors,
  parentKey,
  mount,
  globalDepth,
  apiHidden,
  moreHref,
  hasTrailing,
  openDirs,
  onHoverDir,
  onToggle,
  showAll,
  onRevealAll,
}: {
  nodes: VNode[];
  nodeDepth: number;
  ancestors: boolean[]; // isLast flag per ancestor level, for continuation glyphs
  parentKey: string;
  mount: Mount;
  globalDepth: number;
  apiHidden?: number;
  moreHref?: string;
  hasTrailing?: boolean;
  openDirs: Set<string>;
  onHoverDir: (key: string) => void;
  onToggle: (key: string) => void;
  showAll: Set<string>;
  onRevealAll: (key: string) => void;
}) {
  const visible = showAll.has(parentKey) ? nodes : nodes.slice(0, SHOW_PER_DIR);
  const localHidden = nodes.length - visible.length;
  const syntheticRows = (localHidden > 0 ? 1 : 0) + (apiHidden ? 1 : 0);
  const continuation = ancestors.map((last) => (last ? "   " : "│  ")).join("");

  return (
    <div className={nodeDepth > 0 ? "animate-in fade-in-0 duration-150" : undefined}>
      {visible.map((node, i) => {
        const isLast = i === visible.length - 1 && syntheticRows === 0 && !hasTrailing;
        const glyph = continuation + (isLast ? "└─ " : "├─ ");
        // A dir with nothing in it (and nothing hidden) has nothing to expand
        // — it renders greyed out, the way an empty dir has no weight in a
        // real filesystem. Open when the cursor has touched it, or the
        // scrubber's global floor reaches past its children.
        const isDir = !!node.children && (node.children.length > 0 || !!node.hiddenCount);
        const isEmptyDir = !!node.children && !isDir;
        const open = isDir && (openDirs.has(node.key) || nodeDepth + 1 < globalDepth);
        const rowClass =
          "group flex w-full items-center gap-1.5 rounded-md px-1.5 py-[3px] text-left text-[13px] hover:bg-raised";
        const inner = (
          <>
            <span className="whitespace-pre font-mono text-[12px] leading-none text-muted-foreground/40">
              {glyph}
            </span>
            {isDir ? (
              <ChevronRight
                className={cn(
                  "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
                  open && "rotate-90",
                )}
              />
            ) : (
              <span className="w-3 shrink-0" />
            )}
            <NodeIcon node={node} open={open} />
            <span
              className={cn(
                "truncate",
                isEmptyDir ? "text-muted-foreground" : "text-foreground group-hover:text-brand-700",
              )}
            >
              {node.name}
              {(isDir || isEmptyDir) && <span className="text-muted-foreground">/</span>}
            </span>
            {node.annotation && (
              <span className="shrink-0 pl-1.5 font-mono text-[11px] text-muted-foreground">
                {node.annotation}
              </span>
            )}
          </>
        );
        return (
          <div key={node.key}>
            {isDir ? (
              <button
                type="button"
                onMouseEnter={() => onHoverDir(node.key)}
                onClick={() => onToggle(node.key)}
                aria-expanded={open}
                className={rowClass}
              >
                {inner}
              </button>
            ) : node.href ? (
              <Link href={node.href} className={rowClass}>{inner}</Link>
            ) : (
              <div className={cn(rowClass, "hover:bg-transparent")}>{inner}</div>
            )}
            {isDir && open && (
              <TreeRows
                nodes={node.children!}
                nodeDepth={nodeDepth + 1}
                ancestors={[...ancestors, isLast]}
                parentKey={node.key}
                mount={mount}
                globalDepth={globalDepth}
                apiHidden={node.hiddenCount}
                moreHref={node.moreHref ?? moreHref}
                openDirs={openDirs}
                onHoverDir={onHoverDir}
                onToggle={onToggle}
                showAll={showAll}
                onRevealAll={onRevealAll}
              />
            )}
          </div>
        );
      })}
      {localHidden > 0 && (
        <button
          type="button"
          onClick={() => onRevealAll(parentKey)}
          className="flex w-full items-center gap-1 rounded-md px-1.5 py-1 text-left font-mono text-[12px] text-dim hover:bg-raised hover:text-brand-700"
        >
          <span className="whitespace-pre leading-none text-muted-foreground/40">
            {continuation + (apiHidden ? "├─ " : "└─ ")}
          </span>
          … +{localHidden} more
        </button>
      )}
      {apiHidden ? (
        moreHref ? (
          <Link
            href={moreHref}
            className="flex w-full items-center gap-1 rounded-md px-1.5 py-1 font-mono text-[12px] text-dim hover:bg-raised hover:text-brand-700"
          >
            <span className="whitespace-pre leading-none text-muted-foreground/40">{continuation + "└─ "}</span>
            … {apiHidden} more synced <ArrowUpRight className="h-3 w-3" />
          </Link>
        ) : (
          <div className="flex w-full items-center gap-1 px-1.5 py-1 font-mono text-[12px] text-muted-foreground">
            <span className="whitespace-pre leading-none text-muted-foreground/40">{continuation + "└─ "}</span>
            … {apiHidden} more synced
          </div>
        )
      ) : null}
    </div>
  );
}
