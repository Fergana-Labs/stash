"use client";

import { useEffect, useRef } from "react";
import { useScope } from "@/lib/scope-store";
import { useWorkspace, titleKey, type WorkspaceState } from "@/lib/workspace-store";

const KEY = "moltchat_workspace";

// One-shot migration (2026-08): the layout used to live under a single
// unscoped key. It becomes the personal scope's entry, then the old key dies.
if (typeof window !== "undefined") {
  const legacy = localStorage.getItem(KEY);
  if (legacy !== null && localStorage.getItem(`${KEY}:personal`) === null) {
    localStorage.setItem(`${KEY}:personal`, legacy);
  }
  if (legacy !== null) localStorage.removeItem(KEY);
}

/** The layout slice we persist — references + pane arrangement only, no content.
 *  `titles` rides along because only the active tab's body mounts: without the
 *  cache, background tabs would have no name after a reload until visited. */
type Persisted = Pick<
  WorkspaceState,
  "tabs" | "paneOf" | "activeTabId" | "activeTab1" | "split" | "focusedPane" | "railSection" | "explorerFolderId" | "lastVfsUrl" | "titles"
>;

const EMPTY: Persisted = {
  tabs: [],
  paneOf: {},
  activeTabId: null,
  activeTab1: null,
  split: false,
  focusedPane: 0,
  railSection: "files",
  explorerFolderId: null,
  lastVfsUrl: null,
  titles: {},
};

function readPersisted(storageKey: string): Partial<Persisted> | null {
  const raw = localStorage.getItem(storageKey);
  if (!raw) return null;
  return JSON.parse(raw) as Partial<Persisted>;
}

/**
 * Hydrates the workspace layout from localStorage and writes it back
 * (debounced) on every change. The layout is per scope — each stash keeps its
 * own tabs and comes back exactly as you left it — so a scope switch flushes
 * the old stash's layout and hydrates the new one's. Mount once inside the
 * workspace layout.
 */
export default function Persistence() {
  const scope = useScope();
  const scopeKey = scope?.scope_user_id ?? "personal";
  const hydrated = useRef(false);

  useEffect(() => {
    const storageKey = `${KEY}:${scopeKey}`;
    hydrated.current = false;
    // Fresh baseline first: the previous scope's tabs must not leak into a
    // stash that has none saved.
    useWorkspace.getState().hydrate(EMPTY);
    const saved = readPersisted(storageKey);
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
        lastVfsUrl: s.lastVfsUrl,
        titles: Object.fromEntries(Object.entries(s.titles).filter(([k]) => openKeys.has(k))),
      };
      localStorage.setItem(storageKey, JSON.stringify(slice));
    };
    // A pending debounced write must land before we go away — dropping it
    // leaves stale state in localStorage, which the next mount hydrates back
    // over the live store (e.g. a just-closed tab reappears). On a scope
    // switch this cleanup runs before the new scope's hydrate, so the old
    // stash's layout is saved under its own key first.
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
  }, [scopeKey]);

  return null;
}
