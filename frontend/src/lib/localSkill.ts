import type {
  PublicSkillContents,
  PublicSkillFile,
  PublicSkillPage,
  PublicSkillSubfolder,
  PublicSkillTable,
} from "./api";
import { routes } from "./workspace-routes";

// SKILL.md is the agent manifest inside an explicitly typed skill folder.
export const SKILL_MD = "SKILL.md";

// The backend rejects a SKILL.md whose description is empty, so the scaffold
// seeds description with the name; the user edits it before publishing.
export function skillMdTemplate(name: string): string {
  return `---\nname: ${name}\ndescription: ${name}\n---\n\n# ${name}\n`;
}

// Strip YAML frontmatter from a SKILL.md body for rendering.
export function stripFrontmatter(markdown: string): string {
  if (!markdown.startsWith("---")) return markdown;
  const parts = markdown.split("---");
  if (parts.length < 3) return markdown;
  return parts.slice(2).join("---").trim();
}

export type SkillContentsKind = "page" | "file" | "table" | "folder";

// Canonical public URL for one item inside a skill. The ?skill= query makes the
// /page, /file, /tables, and /folders routes render the item read-only from the
// published skill instead of looking it up in the viewer's own workspace.
const SKILL_ITEM_BASE: Record<SkillContentsKind, (id: string) => string> = {
  page: routes.page,
  file: routes.file,
  table: routes.table,
  folder: routes.folder,
};
export function skillItemPath(
  kind: SkillContentsKind,
  id: string,
  slug: string,
): string {
  return `${SKILL_ITEM_BASE[kind](id)}?skill=${encodeURIComponent(slug)}`;
}

export type SkillContentsItem =
  | PublicSkillPage
  | PublicSkillFile
  | PublicSkillTable
  | PublicSkillSubfolder;

// Locate one object in a public-skill contents payload — used by the
// ?skill= read-only fallbacks on /p, /f, /tables, and folder routes.
export function findInSkillContents(
  contents: PublicSkillContents,
  kind: "page",
  id: string,
): PublicSkillPage | null;
export function findInSkillContents(
  contents: PublicSkillContents,
  kind: "file",
  id: string,
): PublicSkillFile | null;
export function findInSkillContents(
  contents: PublicSkillContents,
  kind: "table",
  id: string,
): PublicSkillTable | null;
export function findInSkillContents(
  contents: PublicSkillContents,
  kind: "folder",
  id: string,
): PublicSkillSubfolder | null;
export function findInSkillContents(
  contents: PublicSkillContents,
  kind: SkillContentsKind,
  id: string,
): SkillContentsItem | null {
  const list: SkillContentsItem[] =
    kind === "page"
      ? contents.pages
      : kind === "file"
        ? contents.files
        : kind === "table"
          ? contents.tables
          : contents.subfolders;
  return list.find((item) => item.id === id) ?? null;
}
