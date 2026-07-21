"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { FolderIcon, PageIcon } from "@/components/SkillIcons";
import type { FolderTreeNode, PageSummary, Tree } from "@/lib/types";
import { routes } from "@/lib/workspace-routes";

/** Total pages in a folder's subtree — the count shown next to each folder. */
export function wikiPageCount(folder: FolderTreeNode): number {
  return (
    folder.pages.length +
    folder.folders.reduce((n, child) => n + wikiPageCount(child), 0)
  );
}

/** Total folders in a tree, all depths. */
export function wikiFolderCount(folders: FolderTreeNode[]): number {
  return folders.reduce((n, f) => n + 1 + wikiFolderCount(f.folders), 0);
}

const INDENT_PX = 18;

/** The Memory wiki rendered as a browsable file system: nested folders with
 *  their pages, every page a link to /p/[pageId]. Folders start expanded so
 *  the whole wiki reads at a glance; click a folder row to collapse it. */
export default function WikiFileTree({ tree }: { tree: Tree }) {
  return (
    <div className="flex flex-col gap-px">
      {tree.folders.map((folder) => (
        <FolderNode key={folder.id} folder={folder} depth={0} />
      ))}
      {tree.pages.map((page) => (
        <PageRow key={page.id} page={page} depth={0} />
      ))}
    </div>
  );
}

function FolderNode({ folder, depth }: { folder: FolderTreeNode; depth: number }) {
  const [open, setOpen] = useState(true);
  const count = wikiPageCount(folder);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-raised"
        style={{ paddingLeft: depth * INDENT_PX + 8 }}
        aria-expanded={open}
      >
        <ChevronRight
          className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform${open ? " rotate-90" : ""}`}
        />
        <span className="shrink-0 text-muted-foreground">
          <FolderIcon />
        </span>
        <span className="truncate font-medium text-foreground">{folder.name}</span>
        <span className="shrink-0 text-[11.5px] text-dim">
          {count === 1 ? "1 page" : `${count} pages`}
        </span>
      </button>
      {open && (
        <div className="flex flex-col gap-px">
          {folder.folders.map((child) => (
            <FolderNode key={child.id} folder={child} depth={depth + 1} />
          ))}
          {folder.pages.map((page) => (
            <PageRow key={page.id} page={page} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function PageRow({ page, depth }: { page: PageSummary; depth: number }) {
  return (
    <Link
      href={`${routes.page(page.id)}?section=memory`}
      className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[13px] text-foreground hover:bg-raised"
      style={{ paddingLeft: depth * INDENT_PX + 8 }}
    >
      {/* Spacer where the folder chevron sits, so page names align with folder names. */}
      <span className="w-3.5 shrink-0" />
      <span className="shrink-0 text-muted-foreground">
        <PageIcon />
      </span>
      <span className="truncate">{page.name}</span>
    </Link>
  );
}
