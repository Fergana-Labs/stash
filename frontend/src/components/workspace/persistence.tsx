"use client";

import { useEffect, useRef } from "react";
import { useWorkspace, titleKey, type WorkspaceState } from "@/lib/workspace-store";

const KEY = "moltchat_workspace";

/** The layout slice we persist — references + pane arrangement only, no content.
 *  `titles` rides along because only the active tab's body mounts: without the
 *  cache, background tabs would have no name after a reload until visited. */
type Persisted = Pick<
  WorkspaceState,
  "tabs" | "paneOf" | "activeTabId" | "activeTab1" | "split" | "focusedPane" | "railSection" | "explorerFolderId" | "titles"
>;

function readPersisted(): Partial<Persisted> | null {
  const raw = localStorage.getItem(KEY);
  if (!raw) return null;
  return JSON.parse(raw) as Partial<Persisted>;
}

/**
 * Hydrates the workspace layout from localStorage on mount and writes it back
 * (debounced) on every change. Mount once inside the workspace layout.
 */
export default function Persistence() {
  const hydrated = useRef(false);

  useEffect(() => {
    const saved = readPersisted();
    if (saved) useWorkspace.getState().hydrate(saved);
    hydrated.current = true;

    let timer: ReturnType<typeof setTimeout> | null = null;
    const write = () => {
      timer = null;
      const s = useWorkspace.getState();
      // Titles for closed tabs are dropped here, so the cache can't grow
      // without bound across sessions.
      const openKeys = new Set(s.tabs.map((t) => titleKey(t.kind, t.refId)));
      const slice: Persisted = {
        tabs: s.tabs,
        paneOf: s.paneOf,
        activeTabId: s.activeTabId,
        activeTab1: s.activeTab1,
        split: s.split,
        focusedPane: s.focusedPane,
        railSection: s.railSection,
        explorerFolderId: s.explorerFolderId,
        titles: Object.fromEntries(Object.entries(s.titles).filter(([k]) => openKeys.has(k))),
      };
      localStorage.setItem(KEY, JSON.stringify(slice));
    };
    // A pending debounced write must land before we go away — dropping it
    // leaves stale state in localStorage, which the next mount hydrates back
    // over the live store (e.g. a just-closed tab reappears).
    const flush = () => {
      if (!timer) return;
      clearTimeout(timer);
      write();
    };
    const unsub = useWorkspace.subscribe(() => {
      if (!hydrated.current) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(write, 1200);
    });
    window.addEventListener("pagehide", flush);

    return () => {
      unsub();
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, []);

  return null;
}
