"use client";

import { useEffect, useRef } from "react";
import { useWorkspace, type WorkspaceState } from "@/lib/workspace-store";

const KEY = "moltchat_workspace";

/** The layout slice we persist — references + pane arrangement only, no content. */
type Persisted = Pick<
  WorkspaceState,
  "tabs" | "paneOf" | "activeTabId" | "activeTab1" | "split" | "focusedPane" | "railSection" | "explorerFolderId"
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
      const slice: Persisted = {
        tabs: s.tabs,
        paneOf: s.paneOf,
        activeTabId: s.activeTabId,
        activeTab1: s.activeTab1,
        split: s.split,
        focusedPane: s.focusedPane,
        railSection: s.railSection,
        explorerFolderId: s.explorerFolderId,
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
