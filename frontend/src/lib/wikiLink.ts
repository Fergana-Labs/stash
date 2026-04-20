/** Wiki-link autocomplete helpers.
 *
 * Links are stored in content_markdown as ordinary markdown links with
 * stable id URLs — `[name](/notebooks?ws=...&nb=...&page=<uuid>)`. This
 * module only handles the authoring-side UX: ranking and labeling
 * suggestions when the user types `[[`.
 */

import type { WorkspacePageEntry } from "./api";

export interface WikiLinkContext {
  /** notebook_id of the page doing the linking, null if unsettled. */
  notebookId: string | null;
  /** folder_id of the page doing the linking, null for root-level. */
  folderId: string | null;
}

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

export function pageHref(page: WorkspacePageEntry, workspaceId: string): string {
  return `/notebooks?ws=${workspaceId}&nb=${page.notebook_id}&page=${page.id}`;
}
