"use client";

import { create } from "zustand";
import { nanoid } from "nanoid";

/**
 * Workspace shell state — the tab strip, split view, rail section, and explorer
 * folder. This is pure window-layout: tabs reference content by (kind, refId),
 * never the content itself. Ported from Fleet's store (the workbench slice),
 * retargeted to moltchat content kinds (no terminal/VPS). Persistence lives in
 * components/workspace/persistence.tsx (localStorage).
 */

export type RailSection = "files" | "agents" | "sessions" | "skills" | "memory" | "tools" | "computer";

export type TabKind = "page" | "file" | "table" | "session" | "sessions-home" | "skill" | "folder" | "agent" | "agent-config" | "tool" | "machine-file" | "terminal";

export interface WorkbenchTab {
  id: string;
  kind: TabKind;
  /** The content id this tab shows: pageId / fileId / tableId / sessionId / skill slug. */
  refId: string;
  title: string;
}

export interface WorkspaceState {
  tabs: WorkbenchTab[];
  activeTabId: string | null;

  // Split view: a second pane. `paneOf` maps tab id → 0 (left) | 1 (right); tabs
  // default to pane 0. `activeTab1` is the right pane's active tab; new tabs open
  // into `focusedPane`.
  split: boolean;
  paneOf: Record<string, 0 | 1>;
  activeTab1: string | null;
  focusedPane: 0 | 1;

  railSection: RailSection;
  /** VFS folder the Files explorer is showing (null = root). */
  explorerFolderId: string | null;

  openTab: (kind: TabKind, refId: string, title: string, opts?: { newTab?: boolean }) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  splitTab: (id: string) => void;
  moveTabToPane: (id: string, pane: 0 | 1) => void;
  setFocusedPane: (pane: 0 | 1) => void;
  renameTab: (id: string, title: string) => void;
  setRailSection: (s: RailSection) => void;
  setExplorerFolderId: (id: string | null) => void;
  hydrate: (data: Partial<WorkspaceState>) => void;
}

/** Place a new tab into the focused pane and make it active there. */
function placeTab(s: WorkspaceState, tab: WorkbenchTab): Partial<WorkspaceState> {
  const pane = s.focusedPane;
  return {
    tabs: [...s.tabs, tab],
    paneOf: { ...s.paneOf, [tab.id]: pane },
    ...(pane === 0 ? { activeTabId: tab.id } : { activeTab1: tab.id, split: true }),
  };
}

/** Focus an existing tab in whichever pane holds it. */
function focusTab(s: WorkspaceState, id: string): Partial<WorkspaceState> {
  const pane = s.paneOf[id] ?? 0;
  return pane === 0 ? { activeTabId: id, focusedPane: 0 } : { activeTab1: id, focusedPane: 1 };
}

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  tabs: [],
  activeTabId: null,
  split: false,
  paneOf: {},
  activeTab1: null,
  focusedPane: 0,
  railSection: "files",
  explorerFolderId: null,

  openTab: (kind, refId, title, opts) => {
    const s = get();
    const existing = s.tabs.find((t) => t.kind === kind && t.refId === refId);
    if (existing) {
      set(focusTab(s, existing.id));
      return;
    }
    // Default is a new tab (deep-links, "new chat", etc. rely on it). Navigation
    // clicks pass newTab:false to replace the current tab in place — unless
    // there's nothing to replace, in which case a new tab is the only option.
    const newTab = opts?.newTab ?? true;
    const activeId = s.focusedPane === 0 ? s.activeTabId : s.activeTab1;
    if (newTab || !activeId) {
      const id = `${kind}-${nanoid(5)}`;
      set(placeTab(s, { id, kind, refId, title }));
      return;
    }
    set({ tabs: s.tabs.map((t) => (t.id === activeId ? { ...t, kind, refId, title } : t)) });
  },

  closeTab: (id) => {
    const s = get();
    const tabs = s.tabs.filter((t) => t.id !== id);
    const paneOf = { ...s.paneOf };
    delete paneOf[id];
    const inPane = (p: 0 | 1) => tabs.filter((t) => (paneOf[t.id] ?? 0) === p);
    const activeTabId = s.activeTabId === id ? inPane(0)[inPane(0).length - 1]?.id ?? null : s.activeTabId;
    let activeTab1 = s.activeTab1 === id ? inPane(1)[inPane(1).length - 1]?.id ?? null : s.activeTab1;
    let { split, focusedPane } = s;
    if (inPane(1).length === 0) {
      split = false;
      activeTab1 = null;
      focusedPane = 0;
    }
    set({ tabs, paneOf, activeTabId, activeTab1, split, focusedPane });
  },

  setActiveTab: (id) => set(focusTab(get(), id)),

  splitTab: (id) => {
    const s = get();
    if ((s.paneOf[id] ?? 0) === 1) return;
    const paneOf = { ...s.paneOf, [id]: 1 as const };
    let activeTabId = s.activeTabId;
    if (activeTabId === id) {
      const pane0 = s.tabs.filter((t) => t.id !== id && (paneOf[t.id] ?? 0) === 0);
      activeTabId = pane0[pane0.length - 1]?.id ?? null;
    }
    set({ paneOf, split: true, activeTab1: id, activeTabId, focusedPane: 1 });
  },

  moveTabToPane: (id, pane) => {
    const s = get();
    if ((s.paneOf[id] ?? 0) === pane) return;
    const paneOf = { ...s.paneOf, [id]: pane };
    const pane1 = s.tabs.filter((t) => (paneOf[t.id] ?? 0) === 1);
    let { activeTabId, activeTab1, split } = s;
    if (pane === 1) {
      split = true;
      activeTab1 = id;
      if (activeTabId === id) {
        const p0 = s.tabs.filter((t) => t.id !== id && (paneOf[t.id] ?? 0) === 0);
        activeTabId = p0[p0.length - 1]?.id ?? null;
      }
    } else {
      activeTabId = id;
      if (activeTab1 === id) activeTab1 = pane1[pane1.length - 1]?.id ?? null;
      if (pane1.length === 0) split = false;
    }
    set({ paneOf, split, activeTabId, activeTab1, focusedPane: pane });
  },

  setFocusedPane: (pane) => set({ focusedPane: pane }),

  renameTab: (id, title) => set({ tabs: get().tabs.map((t) => (t.id === id ? { ...t, title } : t)) }),

  setRailSection: (s) => set({ railSection: s }),

  setExplorerFolderId: (id) => set({ explorerFolderId: id }),

  hydrate: (data) => set({ ...data }),
}));
