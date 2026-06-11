"use client";

import { usePins } from "./pins";

// Pinned items for the Drive page quick-access strip. The kind + route
// are resolved from the loaded items at render time, so folders, pages, tables,
// and files can all be pinned under the one "files" set.
export function useFilePins(workspaceId: string) {
  return usePins("files", workspaceId);
}
