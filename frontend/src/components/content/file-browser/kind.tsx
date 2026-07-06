import { FileIcon, FolderIcon, PageIcon, TableIcon } from "../../SkillIcons";

// "table" = a CSV/spreadsheet *file* linked to a table; "datatable" = a
// standalone structured-data table (the `tables` entity). Both render with the
// table icon, but they have different backing rows so move/delete/nav differ.
export type ItemKind = "folder" | "page" | "html" | "table" | "datatable" | "file";

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
}

export function KindIcon({ kind }: { kind: ItemKind }) {
  if (kind === "folder") return <FolderIcon />;
  if (kind === "page" || kind === "html") return <PageIcon />;
  if (kind === "table" || kind === "datatable") return <TableIcon />;
  return <FileIcon />;
}

export function tintFor(item: GridItem): string {
  if (item.kind === "folder") return "text-muted-foreground";
  if (item.kind === "html") return "text-[#D97706]";
  if (item.kind === "table" || item.kind === "datatable") return "text-emerald-600";
  if (item.contentType?.includes("pdf")) return "text-rose-500";
  if (item.contentType?.startsWith("image/")) return "text-[var(--color-brand-600)]";
  if (item.kind === "page") return "text-[var(--color-brand-600)]";
  return "text-muted-foreground";
}

export function typeFor(item: GridItem): string {
  if (item.kind === "folder") return "Folder";
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
