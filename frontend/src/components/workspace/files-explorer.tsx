"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Loader2, FilePlus, FolderPlus, Upload, Trash2, Pencil, FolderInput,
  Plus, ArrowDownAZ, Clock, FileText, Code2, Table2, GitBranch, GraduationCap, MessagesSquare,
} from "lucide-react";
import {
  getTree, getFolderContents, createPage, createFolder, createTable, updateFolder, updatePage,
  updateFile, updateTable, trashItem, deleteFolder, deleteTable, deleteSessionFolder, updateSessionFolder,
  uploadFileOrPage, importGithubSkill, type FolderBreadcrumb,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace-store";
import { urlForTab } from "@/lib/workspace-routes";
import { FolderIcon, PageIcon, FileIcon, TableIcon } from "@/components/SkillIcons";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

type Kind = "folder" | "page" | "file" | "table" | "skill" | "session-folder" | "session";
export type Item = { kind: Kind; id: string; name: string; ts?: string };
// Kinds that live in the VFS (draggable, rename/move/delete via folder/page APIs).
const VFS_KINDS = new Set<Kind>(["folder", "page", "file", "table", "skill"]);
type Menu = { x: number; y: number; item: Item } | null;
type Sort = "name" | "date";
const DND = "application/x-fx-item";

/** Compact Fleet-style file explorer for the sidebar: breadcrumbs, double-click
 *  to open (folders navigate in; pages/files open as tabs), right-click context
 *  menu, and drag-to-move into folders. Backed by the VFS. */
export default function FilesExplorer({
  onRoot,
  rootLabel = "Files",
  rootFolderId = null,
  hideFolderId = null,
  loadRoot,
  loadFolder,
  newRootItem,
  openRootTab,
  showImport = true,
  vfsWritable = true,
  confirmMemoryWrites = false,
  tabSection,
}: {
  onRoot: () => void;
  rootLabel?: string;
  /** Folder this explorer is rooted at (null = the VFS root). */
  rootFolderId?: string | null;
  /** A root-level folder to hide from the listing (e.g. Memory hidden from Files). */
  hideFolderId?: string | null;
  /** Workspace section stamped on opened tab URLs (?section=) — without it the
   *  shell derives the section from the path, which lands Memory items in
   *  Files (all folder/page routes are files-shaped). */
  tabSection?: string;
  /** Custom root listing (e.g. Skills lists skill folders). Default = the VFS tree. */
  loadRoot?: () => Promise<Item[]>;
  /** Custom folder navigation (e.g. Sessions folders aren't VFS folders). Default =
   *  getFolderContents. */
  loadFolder?: (folderId: string) => Promise<{ crumbs: FolderBreadcrumb[]; items: Item[] }>;
  /** At a virtual root (loadRoot), the "create" action for that root's native item
   *  (e.g. New skill) — replaces new-file/folder/upload, which need a real folder. */
  newRootItem?: { label: string; run: () => Promise<void> };
  /** Double-clicking the root crumb can open a native overview tab. */
  openRootTab?: () => void;
  /** Show the GitHub import button. Default true. */
  showImport?: boolean;
  /** This section can create VFS items (new file/folder/upload). Default true;
   *  Sessions is a read-through view, so false. */
  vfsWritable?: boolean;
  /** Memory is the curator agent's knowledge base, so a manual write there is
   *  unusual: confirm it first and offer to send the item to Files instead. */
  confirmMemoryWrites?: boolean;
}) {
  const router = useRouter();
  const openTab = useWorkspace((s) => s.openTab);
  const [folderId, setFolderId] = useState<string | null>(rootFolderId);

  const [items, setItems] = useState<Item[] | null>(null);
  const [crumbs, setCrumbs] = useState<FolderBreadcrumb[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [menu, setMenu] = useState<Menu>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("name");
  const [importOpen, setImportOpen] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [importing, setImporting] = useState(false);
  // A write action waiting on the "Add to Memory?" confirmation. `run` receives
  // the destination folder: the browsed Memory folder, or null for Files root.
  const [pendingWrite, setPendingWrite] = useState<{ run: (folder: string | null) => Promise<void> } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const clickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      if (folderId === null && loadRoot) {
        setCrumbs([]);
        setItems(await loadRoot());
      } else if (folderId === null) {
        const tree = await getTree();
        setCrumbs([]);
        setItems([
          ...tree.folders.filter((f) => f.id !== hideFolderId).map((f) => ({ kind: "folder" as const, id: f.id, name: f.name, ts: f.updated_at })),
          ...tree.pages.map((p) => ({ kind: "page" as const, id: p.id, name: p.name || "Untitled", ts: p.updated_at })),
        ]);
      } else if (loadFolder) {
        const { crumbs: c, items: it } = await loadFolder(folderId);
        setCrumbs(c);
        setItems(it);
      } else {
        const c = await getFolderContents(folderId);
        setCrumbs(c.breadcrumbs);
        setItems([
          ...c.subfolders.map((f) => ({ kind: "folder" as const, id: f.id, name: f.name })),
          ...c.pages.map((p) => ({ kind: "page" as const, id: p.id, name: p.name || "Untitled", ts: p.created_at })),
          ...c.files.map((f) => ({ kind: "file" as const, id: f.id, name: f.name, ts: f.created_at })),
          ...c.tables.map((t) => ({ kind: "table" as const, id: t.id, name: t.name, ts: t.created_at })),
        ]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, [folderId, hideFolderId, loadRoot, loadFolder]);

  useEffect(() => { setItems(null); load(); }, [load]);
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menu]);

  // Open an item as a workbench tab (folder → folder tab; skill → skill tab; …).
  // Session folders have no tab view, so they only ever navigate in the explorer.
  function openAsTab(item: Item) {
    if (item.kind === "session-folder") { setFolderId(item.id); return; }
    const kind = item.kind === "folder" ? "folder" : item.kind === "skill" ? "skill" : item.kind === "session" ? "session" : item.kind === "table" ? "table" : item.kind === "page" ? "page" : "file";
    openTab(kind, item.id, item.name);
    const suffix = tabSection ? `?section=${tabSection}` : "";
    router.replace(urlForTab({ kind, refId: item.id }) + suffix);
  }

  // Single-click a folder (or skill/session folder) → browse into it in the
  // explorer; double-click → open it as a tab. A short timer lets the dblclick
  // cancel the pending navigate.
  const isFolderLike = (item: Item) => item.kind === "folder" || item.kind === "skill" || item.kind === "session-folder";
  function onRowClick(item: Item) {
    if (!isFolderLike(item)) return;
    if (clickTimer.current) clearTimeout(clickTimer.current);
    clickTimer.current = setTimeout(() => { clickTimer.current = null; setFolderId(item.id); }, 220);
  }
  function onRowDoubleClick(item: Item) {
    if (clickTimer.current) { clearTimeout(clickTimer.current); clickTimer.current = null; }
    openAsTab(item);
  }

  async function move(item: Item, targetFolderId: string | null) {
    if ((item.kind === "folder" || item.kind === "skill") && item.id === targetFolderId) return;
    const body = targetFolderId === null ? { move_to_root: true as const } : undefined;
    if (item.kind === "folder" || item.kind === "skill") await updateFolder(item.id, body ?? { parent_folder_id: targetFolderId! });
    else if (item.kind === "page") await updatePage(item.id, body ?? { folder_id: targetFolderId! });
    else if (item.kind === "table") await updateTable(item.id, body ?? { folder_id: targetFolderId! });
    else await updateFile(item.id, body ?? { folder_id: targetFolderId! });
    await load();
  }

  async function rename(item: Item, name: string) {
    setRenaming(null);
    if (!name.trim() || name === item.name) return;
    if (item.kind === "folder" || item.kind === "skill") await updateFolder(item.id, { name });
    else if (item.kind === "session-folder") await updateSessionFolder(item.id, { name });
    else if (item.kind === "session") return;
    else if (item.kind === "page") await updatePage(item.id, { name });
    else if (item.kind === "table") await updateTable(item.id, { name });
    else await updateFile(item.id, { name });
    await load();
  }

  async function del(item: Item) {
    if (item.kind === "folder" || item.kind === "skill") await deleteFolder(item.id);
    else if (item.kind === "session-folder") await deleteSessionFolder(item.id);
    else if (item.kind === "table") await deleteTable(item.id);
    else await trashItem(item.kind, item.id); // page | file | session
    await load();
  }

  // In Memory, every create/upload goes through the "Add to Memory?" dialog;
  // everywhere else the action runs immediately in the browsed folder.
  function guardWrite(run: (folder: string | null) => Promise<void>) {
    if (confirmMemoryWrites) setPendingWrite({ run });
    else void run(folderId);
  }
  async function newDoc(contentType: "markdown" | "html", folder: string | null) {
    const p = await createPage("Untitled", folder, "", { content_type: contentType });
    await load();
    openAsTab({ kind: "page", id: p.id, name: "Untitled" });
  }
  async function newTableItem(folder: string | null) {
    const t = await createTable("Untitled table");
    if (folder) await updateTable(t.id, { folder_id: folder });
    await load();
    openAsTab({ kind: "table", id: t.id, name: t.name });
  }
  async function newFolder(folder: string | null) { await createFolder("New folder", folder); await load(); }
  async function runNewRootItem() { if (!newRootItem) return; await newRootItem.run(); await load(); }
  async function uploadFiles(files: File[], folder: string | null) {
    for (const f of files) await uploadFileOrPage(f, folder ?? undefined);
    await load();
  }
  function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (fileRef.current) fileRef.current.value = "";
    if (files.length === 0) return;
    guardWrite((folder) => uploadFiles(files, folder));
  }
  async function doImport() {
    if (!repoUrl.trim()) return;
    setImporting(true);
    try {
      const r = await importGithubSkill(repoUrl.trim());
      toast.success(`Imported ${r.imported} skill${r.imported !== 1 ? "s" : ""} from GitHub`);
      setImportOpen(false);
      setRepoUrl("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  // A virtual root (Skills list) has no folder to create loose files into.
  const atVirtualRoot = !!loadRoot && folderId === rootFolderId;

  const sortedItems = items && [...items].sort((a, b) => {
    // Folders always first.
    if ((a.kind === "folder") !== (b.kind === "folder")) return a.kind === "folder" ? -1 : 1;
    if (sort === "date") return (b.ts ?? "").localeCompare(a.ts ?? "");
    return a.name.localeCompare(b.name);
  });

  const ToolBtn = ({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) => (
    <button onClick={onClick} title={label} aria-label={label} className="flex h-7 w-7 items-center justify-center rounded text-sidebar-foreground hover:bg-sidebar-accent">{icon}</button>
  );

  return (
    <div className="flex h-full flex-col">
      {/* Breadcrumb + actions on one row (shadcn-style). */}
      <div className="flex h-9 shrink-0 items-center gap-1 border-b border-[var(--divider-color)] px-2 text-[12px]">
        <button onClick={onRoot} className="shrink-0 text-muted-foreground hover:text-foreground">Home</button>
        <span className="text-muted-foreground/50">/</span>
        <button
          onClick={() => setFolderId(rootFolderId)}
          onDoubleClick={openRootTab}
          className={cn("shrink-0 hover:text-foreground", folderId === rootFolderId ? "font-medium text-foreground" : "text-muted-foreground")}
        >
          {rootLabel}
        </button>
        {(rootFolderId ? crumbs.slice(crumbs.findIndex((c) => c.id === rootFolderId) + 1) : crumbs).map((c, i, arr) => (
          <span key={c.id} className="flex min-w-0 items-center gap-1">
            <span className="text-muted-foreground/50">/</span>
            <button onClick={() => setFolderId(c.id)} className={cn("min-w-0 truncate hover:text-foreground", i === arr.length - 1 ? "font-medium text-foreground" : "text-muted-foreground")}>{c.name}</button>
          </span>
        ))}
        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          {atVirtualRoot ? (
            newRootItem && (
              <button title={newRootItem.label} aria-label={newRootItem.label} onClick={runNewRootItem} className="flex h-7 items-center gap-1 rounded px-1.5 text-[12px] text-sidebar-foreground hover:bg-sidebar-accent">
                <FolderPlus className="h-4 w-4" /><Plus className="h-2.5 w-2.5" />
              </button>
            )
          ) : vfsWritable ? (
            <>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button title="New file" aria-label="New file" className="flex h-7 items-center gap-0.5 rounded px-1.5 text-sidebar-foreground hover:bg-sidebar-accent">
                    <FilePlus className="h-4 w-4" /><Plus className="h-2.5 w-2.5" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => guardWrite((f) => newDoc("markdown", f))}><FileText className="h-4 w-4" /> Markdown page</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => guardWrite((f) => newDoc("html", f))}><Code2 className="h-4 w-4" /> HTML page</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => guardWrite(newTableItem)}><Table2 className="h-4 w-4" /> Table</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <ToolBtn icon={<FolderPlus className="h-4 w-4" />} label="New folder" onClick={() => guardWrite(newFolder)} />
              <ToolBtn icon={<Upload className="h-4 w-4" />} label="Upload" onClick={() => fileRef.current?.click()} />
            </>
          ) : null}
          {showImport && <ToolBtn icon={<GitBranch className="h-4 w-4" />} label="Import from GitHub" onClick={() => setImportOpen(true)} />}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button title="Sort" aria-label="Sort" className="flex h-7 w-7 items-center justify-center rounded text-sidebar-foreground hover:bg-sidebar-accent">
                {sort === "date" ? <Clock className="h-4 w-4" /> : <ArrowDownAZ className="h-4 w-4" />}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setSort("name")}><ArrowDownAZ className="h-4 w-4" /> Name {sort === "name" && <span className="ml-auto text-brand-600">✓</span>}</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSort("date")}><Clock className="h-4 w-4" /> Date modified {sort === "date" && <span className="ml-auto text-brand-600">✓</span>}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <input ref={fileRef} type="file" multiple className="hidden" onChange={onUpload} />
        </div>
      </div>

      {/* List — root is also a drop target (move to root) */}
      <div
        className="min-h-0 flex-1 overflow-y-auto pt-1 pb-24"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { const raw = e.dataTransfer.getData(DND); if (raw) void move(JSON.parse(raw) as Item, folderId); }}
      >
        {error && <div className="px-3 py-2 text-[12px] text-destructive">{error}</div>}
        {!items && !error && <div className="flex items-center gap-2 px-3 py-2 text-[12px] text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading…</div>}
        {sortedItems?.length === 0 && <div className="px-3 py-2 text-[12px] text-muted-foreground">Empty folder.</div>}
        {sortedItems?.map((item) => {
          const isFolder = item.kind === "folder" || item.kind === "skill";
          return (
            <div
              key={`${item.kind}-${item.id}`}
              draggable={renaming !== item.id && VFS_KINDS.has(item.kind)}
              onDragStart={(e) => e.dataTransfer.setData(DND, JSON.stringify(item))}
              onDragOver={isFolder ? (e) => { e.preventDefault(); setDropTarget(item.id); } : undefined}
              onDragLeave={isFolder ? () => setDropTarget((t) => (t === item.id ? null : t)) : undefined}
              onDrop={isFolder ? (e) => { e.preventDefault(); e.stopPropagation(); setDropTarget(null); const raw = e.dataTransfer.getData(DND); if (raw) void move(JSON.parse(raw) as Item, item.id); } : undefined}
              onClick={() => onRowClick(item)}
              onDoubleClick={() => onRowDoubleClick(item)}
              onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY, item }); }}
              className={cn(
                "group flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-[13px] text-sidebar-foreground hover:bg-sidebar-accent",
                dropTarget === item.id && "ring-1 ring-brand-400",
              )}
              title={item.name}
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center text-muted-foreground">
                {item.kind === "skill" ? <GraduationCap className="h-3.5 w-3.5 text-chart-4" /> : item.kind === "session-folder" ? <FolderIcon className="text-[13px] text-chart-4" /> : item.kind === "session" ? <MessagesSquare className="h-3.5 w-3.5" /> : item.kind === "folder" ? <FolderIcon className="text-[13px] text-chart-4" /> : item.kind === "page" ? <PageIcon className="text-[13px]" /> : item.kind === "table" ? <TableIcon className="text-[13px]" /> : <FileIcon className="text-[13px]" />}
              </span>
              {renaming === item.id ? (
                <input
                  autoFocus
                  defaultValue={item.name}
                  onClick={(e) => e.stopPropagation()}
                  onBlur={(e) => rename(item, e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") setRenaming(null); }}
                  className="min-w-0 flex-1 rounded border border-brand-400 bg-base px-1 text-[13px] outline-none"
                />
              ) : (
                <span className="min-w-0 flex-1 truncate">{item.name}</span>
              )}
            </div>
          );
        })}
      </div>

      {menu && (
        <div className="fixed z-50 w-40 overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg" style={{ left: menu.x, top: menu.y }} onClick={(e) => e.stopPropagation()}>
          <button onClick={() => { const it = menu.item; setMenu(null); if (isFolderLike(it)) setFolderId(it.id); else openAsTab(it); }} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-foreground hover:bg-raised"><FolderInput className="h-3.5 w-3.5" /> Open</button>
          {(menu.item.kind === "folder" || menu.item.kind === "skill") && <button onClick={() => { const it = menu.item; setMenu(null); openAsTab(it); }} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-foreground hover:bg-raised"><FolderInput className="h-3.5 w-3.5" /> Open in tab</button>}
          {menu.item.kind !== "session" && <button onClick={() => { setRenaming(menu.item.id); setMenu(null); }} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-foreground hover:bg-raised"><Pencil className="h-3.5 w-3.5" /> Rename</button>}
          <button onClick={async () => { const it = menu.item; setMenu(null); await del(it); }} className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-destructive hover:bg-raised"><Trash2 className="h-3.5 w-3.5" /> Delete</button>
        </div>
      )}

      <Dialog open={!!pendingWrite} onOpenChange={(open) => { if (!open) setPendingWrite(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add to Memory?</DialogTitle></DialogHeader>
          <p className="text-[13px] text-muted-foreground">
            Memory is your curator agent&apos;s knowledge base — it&apos;s usually maintained
            automatically, not by hand. Most files belong in Files.
          </p>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => { const w = pendingWrite!; setPendingWrite(null); void w.run(folderId); }}
            >
              Add to Memory anyway
            </Button>
            <Button
              onClick={async () => { const w = pendingWrite!; setPendingWrite(null); await w.run(null); toast.success("Added to Files"); }}
            >
              Add to Files instead
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Import from GitHub</DialogTitle></DialogHeader>
          <p className="text-[13px] text-muted-foreground">Paste a public repo URL to import its <code>SKILL.md</code> folders as Skills.</p>
          <Input placeholder="https://github.com/owner/repo" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void doImport(); }} />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setImportOpen(false)}>Cancel</Button>
            <Button onClick={doImport} disabled={importing}>{importing ? "Importing…" : "Import"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
