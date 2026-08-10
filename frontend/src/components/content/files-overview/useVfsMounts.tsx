"use client";

// The one VFS, loaded and shaped once for two surfaces: the full-screen
// /files lens and the docked sidebar tree render these same mounts, so what
// you saw full-screen is exactly what appears on the left after you click.

import { ReactNode, useEffect, useMemo, useState } from "react";
import { Brain, Cable, FolderTree, GraduationCap, MessagesSquare } from "lucide-react";
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
import { cn } from "@/lib/utils";
import {
  buildFilesNodes,
  buildSessionNodes,
  buildSkillNodes,
  buildSourceNodes,
  type VNode,
} from "./build";

const RECENT_SESSIONS = 8;

export interface Mount {
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
  vitals: MeOverview;
}

export function NodeIcon({ node, open }: { node: VNode; open: boolean }) {
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

export function useVfsMounts(): {
  mounts: Mount[];
  coreLoaded: boolean;
  coreError: string | null;
  sourcesPending: boolean;
  sourcesError: string | null;
} {
  const [core, setCore] = useState<CoreData | null>(null);
  const [coreError, setCoreError] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceTreeRoot[] | null>(null);
  const [sourcesError, setSourcesError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getSidebar(), listTables(), listSkills(), getMeOverview(), getMemoryFolder()])
      .then(([sidebar, tables, skills, vitals, memoryFolder]) => {
        if (cancelled) return;
        const { files, memory } = buildFilesNodes(sidebar.files, memoryFolder.id, tables.tables);
        setCore({
          filesNodes: files,
          memoryFolderId: memoryFolder.id,
          memoryNodes: memory,
          sessionNodes: buildSessionNodes(sidebar.sessions.slice(0, RECENT_SESSIONS)),
          skillNodes: buildSkillNodes(skills),
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
          // ?section=files keeps the VFS docked when a provider opens from
          // either VFS surface, instead of teleporting to the Tools section.
          href: `/integrations/${provider}?section=files`,
          children: nodes,
          hiddenCount: hiddenCount || undefined,
          moreHref: `/integrations/${provider}?section=files`,
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

  return {
    mounts,
    coreLoaded: core !== null,
    coreError,
    sourcesPending: sources === null && !sourcesError,
    sourcesError,
  };
}
