/** Wiki-link path resolution.
 *
 * Link syntax (filesystem-like — no implicit fallback to other folders):
 *   [[page]]                     → current notebook, current folder
 *   [[folder/page]]              → current notebook, named folder
 *   [[notebook/page]]            → named notebook, root (if no folder matches)
 *   [[notebook/folder/page]]     → named notebook, named folder
 *
 * 2-segment links are ambiguous between `folder/page` in the current
 * notebook and `notebook/page` (at that notebook's root). We prefer
 * the folder interpretation first (locality beats cross-notebook);
 * only fall through to the notebook interpretation if no folder match.
 *
 * The `name` portion is always the file part of the page (the value of
 * notebook_pages.name in the DB). We never strip extensions — you
 * literally link `[[README.md]]`.
 */

import type { WorkspacePageEntry } from "./api";

export interface WikiLinkContext {
  /** notebook_id of the page the link lives on; null when the editor
   *  hasn't settled on a page yet (e.g. empty new page). */
  notebookId: string | null;
  /** folder_id of the page the link lives on; null for root-level pages. */
  folderId: string | null;
}

export type WikiLinkResolution =
  | { status: "resolved"; page: WorkspacePageEntry }
  | { status: "ambiguous"; candidates: WorkspacePageEntry[] }
  | { status: "unresolved" };

/** Parse a link's raw text (everything between `[[` and `]]`) into path
 *  parts. Whitespace around each segment is trimmed. */
export function parseLinkText(raw: string): string[] {
  return raw
    .split("/")
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

/** Resolve a link against the workspace page index and the current
 *  editing context. Returns the matched page, an ambiguity list, or an
 *  unresolved marker so the UI can render accordingly. */
export function resolveWikiLink(
  rawLinkText: string,
  index: WorkspacePageEntry[],
  ctx: WikiLinkContext
): WikiLinkResolution {
  const parts = parseLinkText(rawLinkText);
  if (parts.length === 0) return { status: "unresolved" };

  // 3 parts → notebook / folder / page (fully qualified).
  if (parts.length >= 3) {
    const [notebook, folder, ...rest] = parts;
    const name = rest.join("/");
    return finalize(
      index.filter(
        (p) =>
          p.notebook_name === notebook &&
          (p.folder_name ?? "") === folder &&
          p.name === name
      )
    );
  }

  // 2 parts → try folder-in-current-notebook first, then notebook-root.
  if (parts.length === 2) {
    const [first, second] = parts;
    if (ctx.notebookId) {
      const folderHits = index.filter(
        (p) =>
          p.notebook_id === ctx.notebookId &&
          p.folder_name === first &&
          p.name === second
      );
      if (folderHits.length > 0) return finalize(folderHits);
    }
    const notebookHits = index.filter(
      (p) =>
        p.notebook_name === first &&
        p.folder_id === null &&
        p.name === second
    );
    return finalize(notebookHits);
  }

  // 1 part → name only. Prefer the current folder (filesystem-local);
  // fall back to a workspace-wide unique match so old-style
  // `[[Page]]` links from imports still resolve when they're
  // unambiguous. Multiple matches → ambiguous (caller can decide).
  const [name] = parts;
  if (ctx.notebookId) {
    const local = index.filter(
      (p) =>
        p.notebook_id === ctx.notebookId &&
        p.folder_id === ctx.folderId &&
        p.name === name
    );
    if (local.length > 0) return finalize(local);
  }
  const anywhere = index.filter((p) => p.name === name);
  return finalize(anywhere);
}

function finalize(hits: WorkspacePageEntry[]): WikiLinkResolution {
  if (hits.length === 0) return { status: "unresolved" };
  if (hits.length === 1) return { status: "resolved", page: hits[0] };
  return { status: "ambiguous", candidates: hits };
}

/** Format a page as the canonical shortest-unique path string to display
 *  in autocomplete: `page` if same folder as ctx, `folder/page` if same
 *  notebook but different folder, `notebook/folder/page` or
 *  `notebook/page` otherwise. Folder-less root pages drop the folder
 *  segment entirely. */
export function formatPagePath(
  page: WorkspacePageEntry,
  ctx: WikiLinkContext
): string {
  const sameNotebook = page.notebook_id === ctx.notebookId;
  const sameFolder = sameNotebook && page.folder_id === ctx.folderId;
  if (sameFolder) return page.name;
  if (sameNotebook) {
    return page.folder_name ? `${page.folder_name}/${page.name}` : page.name;
  }
  if (page.folder_name) {
    return `${page.notebook_name}/${page.folder_name}/${page.name}`;
  }
  return `${page.notebook_name}/${page.name}`;
}

/** Rank candidate pages for autocomplete: same folder > same notebook >
 *  anything else. Ties broken by last-updated (most recent first). */
export function rankForAutocomplete(
  pages: WorkspacePageEntry[],
  ctx: WikiLinkContext
): WorkspacePageEntry[] {
  const score = (p: WorkspacePageEntry) => {
    if (p.notebook_id === ctx.notebookId && p.folder_id === ctx.folderId) return 0;
    if (p.notebook_id === ctx.notebookId) return 1;
    return 2;
  };
  return [...pages].sort((a, b) => {
    const s = score(a) - score(b);
    if (s !== 0) return s;
    return b.updated_at.localeCompare(a.updated_at);
  });
}
