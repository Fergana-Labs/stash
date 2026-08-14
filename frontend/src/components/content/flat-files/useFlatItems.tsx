"use client";

// The flat-list VFS experiment: the whole stash as one searchable,
// reverse-chronological list — no hierarchy. Folder location survives only as
// a dim context label on each row. Agents still get the real filesystem
// through the CLI VFS; this is the human lens.

import { useEffect, useState } from "react";
import { GraduationCap, MessagesSquare } from "lucide-react";
import {
  getMemoryFolder,
  getSidebar,
  listSkills,
  listTables,
  type Sidebar,
  type Skill,
  type TreeFolder,
} from "@/lib/api";
import type { Table } from "@/lib/types";
import { FileIcon, PageIcon, TableIcon } from "@/components/SkillIcons";
import { humanSize } from "@/components/content/files-overview/build";

export type FlatKind = "page" | "file" | "table" | "session" | "skill";

export interface FlatItem {
  key: string;
  kind: FlatKind;
  name: string;
  href: string;
  /** Where it lives, in words: the folder path. */
  context?: string;
  /** Agent it came from — the session's agent, or a page's last agent editor. */
  agent?: string;
  /** Dim mono note — "12 KB", "8 rows", "4 files". */
  annotation?: string;
  updatedAt: string;
}

export function FlatItemIcon({ kind }: { kind: FlatKind }) {
  if (kind === "page") return <span className="shrink-0 text-muted-foreground"><PageIcon /></span>;
  if (kind === "table") return <span className="shrink-0 text-muted-foreground"><TableIcon /></span>;
  if (kind === "session") return <MessagesSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
  if (kind === "skill") return <GraduationCap className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
  return <span className="shrink-0 text-muted-foreground"><FileIcon /></span>;
}

/** Full "A / B / C" location for every folder, in one pass. */
function folderPaths(folders: TreeFolder[]): Map<string, string> {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const paths = new Map<string, string>();
  function pathOf(id: string): string {
    const cached = paths.get(id);
    if (cached) return cached;
    const folder = byId.get(id);
    // Parents can be invisible (skill subtrees, unreadable folders); the
    // path then starts at the first visible ancestor.
    if (!folder) return "";
    const parent = folder.parent_folder_id ? pathOf(folder.parent_folder_id) : "";
    const path = parent ? `${parent} / ${folder.name}` : folder.name;
    paths.set(id, path);
    return path;
  }
  folders.forEach((f) => pathOf(f.id));
  return paths;
}

/** The memory folder and every folder under it. */
function memorySubtree(folders: TreeFolder[], memoryFolderId: string): Set<string> {
  const ids = new Set([memoryFolderId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const f of folders) {
      if (f.parent_folder_id && ids.has(f.parent_folder_id) && !ids.has(f.id)) {
        ids.add(f.id);
        grew = true;
      }
    }
  }
  return ids;
}

function buildFlatItems(
  sidebar: Sidebar,
  tables: Table[],
  skills: Skill[],
  memoryFolderId: string,
): FlatItem[] {
  // Memory is a derived layer over the stash, not ground truth — the whole
  // subtree is invisible here (part of the never-show-memory experiment).
  const memoryIds = memorySubtree(sidebar.files.folders, memoryFolderId);
  const inMemory = (folderId: string | null) => folderId !== null && memoryIds.has(folderId);

  const paths = folderPaths(sidebar.files.folders);
  const context = (folderId: string | null) => (folderId ? paths.get(folderId) : undefined);

  const pages = sidebar.files.pages.filter((p) => !inMemory(p.folder_id)).map<FlatItem>((p) => ({
    key: `page:${p.id}`,
    kind: "page",
    name: p.name,
    href: `/p/${p.id}`,
    context: context(p.folder_id),
    agent: p.last_edit_agent_name ?? undefined,
    updatedAt: p.updated_at,
  }));
  const files = sidebar.files.files.filter((f) => !inMemory(f.folder_id)).map<FlatItem>((f) => ({
    key: `file:${f.id}`,
    kind: "file",
    name: f.name,
    href: `/f/${f.id}`,
    context: context(f.folder_id),
    annotation: humanSize(f.size_bytes),
    updatedAt: f.created_at,
  }));
  const tableItems = tables.filter((t) => !inMemory(t.folder_id)).map<FlatItem>((t) => ({
    key: `table:${t.id}`,
    kind: "table",
    name: t.name,
    href: `/tables/${t.id}`,
    context: context(t.folder_id),
    annotation: `${t.row_count ?? 0} row${t.row_count === 1 ? "" : "s"}`,
    updatedAt: t.updated_at,
  }));
  const sessions = sidebar.sessions.map<FlatItem>((s) => ({
    key: `session:${s.session_id}`,
    kind: "session",
    name: s.title || s.agent_name || "session",
    href: `/sessions/${s.session_id}`,
    agent: s.agent_name || undefined,
    updatedAt: s.last_at,
  }));
  const skillItems = skills.map<FlatItem>((s) => ({
    key: `skill:${s.folder_id}`,
    kind: "skill",
    name: s.name,
    href: `/skills/folder/${s.folder_id}`,
    annotation: `${s.file_count} file${s.file_count === 1 ? "" : "s"}`,
    updatedAt: s.updated_at,
  }));

  return [...pages, ...files, ...tableItems, ...sessions, ...skillItems].sort(
    (a, b) => +new Date(b.updatedAt) - +new Date(a.updatedAt),
  );
}

/** Rank matches: name prefix, then name substring, then location/agent
 *  substring. Within a rank the list keeps its recency order (Array.sort is
 *  stable). */
export function filterItems(items: FlatItem[], query: string): FlatItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  const scored: { item: FlatItem; score: number }[] = [];
  for (const item of items) {
    const name = item.name.toLowerCase();
    const rest = `${item.context ?? ""} ${item.agent ?? ""}`.toLowerCase();
    if (name.startsWith(q)) scored.push({ item, score: 0 });
    else if (name.includes(q)) scored.push({ item, score: 1 });
    else if (rest.includes(q)) scored.push({ item, score: 2 });
  }
  return scored.sort((a, b) => a.score - b.score).map((s) => s.item);
}

export function useFlatItems(): { items: FlatItem[]; loaded: boolean; error: string | null } {
  const [items, setItems] = useState<FlatItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getSidebar(), listTables(), listSkills(), getMemoryFolder()])
      .then(([sidebar, tables, skills, memoryFolder]) => {
        if (cancelled) return;
        setItems(buildFlatItems(sidebar, tables.tables, skills, memoryFolder.id));
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, []);

  return { items: items ?? [], loaded: items !== null, error };
}
