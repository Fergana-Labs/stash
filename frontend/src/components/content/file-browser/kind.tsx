import type { ReactNode } from "react";
import { GraduationCap, MessagesSquare } from "lucide-react";
import { FileIcon, FolderIcon, PageIcon, TableIcon } from "../../SkillIcons";

// "table" = a CSV/spreadsheet *file* linked to a table; "datatable" = a
// standalone structured-data table (the `tables` entity). Both render with the
// table icon, but they have different backing rows so move/delete/nav differ.
// The last three are VFS mounts that are not files: /sessions, /skills, and
// the documents inside /sources. They list in the same browser as files
// because that is what the VFS shows an agent, but they are not stored as
// files and carry none of the file operations.
export type ItemKind =
  | "folder"
  | "page"
  | "html"
  | "table"
  | "datatable"
  | "file"
  | "session"
  | "skill"
  | "source-doc";

export interface GridItem {
  kind: ItemKind;
  id: string;
  name: string;
  subtitle: string;
  sizeBytes?: number;
  contentType?: string;
  tableId?: string;
  tableBackedBy?: "file" | "table";
  linkedTableId?: string;
  movable?: boolean;
  /** ISO timestamp. Renders as "Modified" in the Drive-style List view.
   *  Not all rows have one — FolderContents.pages currently omits it. */
  updatedAt?: string;
  /** The one secondary fact worth a column in this listing — the agent that
   *  ran a session, what a skill contains. Rendered only when the caller asks
   *  for a detail column. */
  detail?: string;
  /** Row icon that overrides the kind icon — connected sources wear their
   *  own brand mark, which is how you tell gmail from slack at a glance. */
  icon?: ReactNode;
}

export function KindIcon({ kind }: { kind: ItemKind }) {
  if (kind === "folder") return <FolderIcon />;
  if (kind === "page" || kind === "html") return <PageIcon />;
  if (kind === "table" || kind === "datatable") return <TableIcon />;
  if (kind === "session") return <MessagesSquare className="h-[15px] w-[15px]" />;
  if (kind === "skill") return <GraduationCap className="h-[15px] w-[15px]" />;
  return <FileIcon />;
}

export function tintFor(item: GridItem): string {
  if (item.kind === "folder") return "text-muted-foreground";
  if (item.kind === "session") return "text-chart-1";
  if (item.kind === "skill") return "text-chart-3";
  if (item.kind === "source-doc") return "text-muted-foreground";
  if (item.kind === "html") return "text-[#D97706]";
  if (item.kind === "table" || item.kind === "datatable") return "text-emerald-600";
  if (item.contentType?.includes("pdf")) return "text-rose-500";
  if (item.contentType?.startsWith("image/")) return "text-[var(--color-brand-600)]";
  if (item.kind === "page") return "text-[var(--color-brand-600)]";
  return "text-muted-foreground";
}

export function typeFor(item: GridItem): string {
  if (item.kind === "folder") return "Folder";
  if (item.kind === "session") return "Session";
  if (item.kind === "skill") return "Skill";
  if (item.kind === "source-doc") return "Document";
  if (item.kind === "table" || item.kind === "datatable") return "Table";
  if (item.kind === "html") return "HTML";
  if (item.kind === "page") return "Markdown";
  if (item.contentType?.includes("pdf")) return "PDF";
  if (item.contentType?.includes("csv")) return "CSV";
  if (item.contentType?.startsWith("image/")) {
    return item.contentType.replace("image/", "").toUpperCase();
  }
  return item.contentType || "File";
}
