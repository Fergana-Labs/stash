// Pure data shaping for the /files bird's-eye view: every mount (files,
// memory, sessions, skills, tables, connected sources) is normalized into one
// VNode tree so a single renderer can draw the whole stash.

import type { ReactNode } from "react";
import type {
  FilesTree,
  SidebarSession,
  Skill,
  SourceTreeEntry,
  TreeFolder,
} from "@/lib/api";
import type { Table } from "@/lib/types";

export type VNodeKind =
  | "folder"
  | "page"
  | "file"
  | "table"
  | "session"
  | "skill"
  | "source-doc";

export interface VNode {
  key: string;
  kind: VNodeKind;
  name: string;
  /** Deep link into the product; absent for rows with no in-app view (source docs). */
  href?: string;
  /** Dim note after the name — "4 pages", "12 rows", "2h ago". */
  annotation?: string;
  children?: VNode[];
  /** Rows the API itself cut off (sources tree per-dir cap). */
  hiddenCount?: number;
  /** Custom row icon (provider brand marks); falls back to the kind icon. */
  icon?: ReactNode;
  /** Where this subtree's "+N more" rows should take the user. */
  moreHref?: string;
}

function byName<T extends { name: string }>(a: T, b: T): number {
  return a.name.localeCompare(b.name);
}

export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)}d ago`;
  return `${Math.floor(seconds / (86400 * 30))}mo ago`;
}

function folderAnnotation(folder: TreeFolder): string | undefined {
  const parts = [];
  if (folder.page_count > 0) parts.push(`${folder.page_count} page${folder.page_count === 1 ? "" : "s"}`);
  if (folder.file_count > 0) parts.push(`${folder.file_count} file${folder.file_count === 1 ? "" : "s"}`);
  return parts.length ? parts.join(", ") : undefined;
}

/** Nest the flat sidebar tree into VNodes, splitting the Memory subtree out
 *  into its own mount (Memory is a reserved folder presented as its own root,
 *  exactly like the VFS does). */
export function buildFilesNodes(
  tree: FilesTree,
  memoryFolderId: string,
  tables: Table[],
): { files: VNode[]; memory: VNode[] } {
  const childFolders = new Map<string | null, TreeFolder[]>();
  for (const folder of tree.folders) {
    const list = childFolders.get(folder.parent_folder_id) ?? [];
    list.push(folder);
    childFolders.set(folder.parent_folder_id, list);
  }

  function folderNode(folder: TreeFolder): VNode {
    return {
      key: folder.id,
      kind: "folder",
      name: folder.name,
      href: `/folders/${folder.id}`,
      annotation: folderAnnotation(folder),
      children: childrenOf(folder.id),
    };
  }

  function childrenOf(folderId: string | null): VNode[] {
    const folders = (childFolders.get(folderId) ?? [])
      .filter((f) => f.id !== memoryFolderId)
      .sort(byName)
      .map(folderNode);
    const pages = tree.pages
      .filter((p) => p.folder_id === folderId)
      .sort(byName)
      .map<VNode>((p) => ({ key: p.id, kind: "page", name: p.name, href: `/p/${p.id}` }));
    const files = tree.files
      .filter((f) => f.folder_id === folderId)
      .sort(byName)
      .map<VNode>((f) => ({
        key: f.id,
        kind: "file",
        name: f.name,
        href: `/f/${f.id}`,
        annotation: humanSize(f.size_bytes),
      }));
    // Tables live in the folder tree like anything else — same as the VFS.
    const tableNodes = tables
      .filter((t) => t.folder_id === folderId)
      .sort(byName)
      .map<VNode>((t) => ({
        key: t.id,
        kind: "table",
        name: t.name,
        href: `/tables/${t.id}`,
        annotation: `${t.row_count ?? 0} row${t.row_count === 1 ? "" : "s"}`,
      }));
    return [...folders, ...pages, ...files, ...tableNodes];
  }

  return { files: childrenOf(null), memory: childrenOf(memoryFolderId) };
}

export function buildSessionNodes(sessions: SidebarSession[]): VNode[] {
  return sessions.map((s) => ({
    key: s.session_id,
    kind: "session",
    name: s.title || s.agent_name || "session",
    href: `/sessions/${s.session_id}`,
    annotation: [s.agent_name, timeAgo(s.last_at)].filter(Boolean).join(", "),
  }));
}

export function buildSkillNodes(skills: Skill[]): VNode[] {
  return [...skills].sort(byName).map((s) => ({
    key: s.folder_id,
    kind: "skill",
    name: s.name,
    href: `/skills/folder/${s.folder_id}`,
    annotation: [
      `${s.file_count} file${s.file_count === 1 ? "" : "s"}`,
      s.published ? "published" : null,
    ]
      .filter(Boolean)
      .join(", "),
  }));
}

/** Convert one source's entry tree. Truncation markers become the parent's
 *  hiddenCount instead of a child row, so the renderer owns the "+N more" UI. */
export function buildSourceNodes(entries: SourceTreeEntry[], keyPrefix: string): {
  nodes: VNode[];
  hiddenCount: number;
} {
  let hiddenCount = 0;
  const nodes: VNode[] = [];
  entries.forEach((entry, index) => {
    if (entry.kind === "truncated") {
      hiddenCount += entry.hidden ?? 0;
      return;
    }
    const key = `${keyPrefix}/${entry.path ?? entry.name}#${index}`;
    if (entry.children) {
      const child = buildSourceNodes(entry.children, key);
      nodes.push({
        key,
        kind: "folder",
        name: entry.name,
        annotation: annotateDir(child),
        children: child.nodes,
        hiddenCount: child.hiddenCount || undefined,
      });
      return;
    }
    nodes.push({ key, kind: "source-doc", name: entry.name });
  });
  return { nodes, hiddenCount };
}

function annotateDir(child: { nodes: VNode[]; hiddenCount: number }): string {
  const total = child.nodes.length + child.hiddenCount;
  return `${total} item${total === 1 ? "" : "s"}`;
}

