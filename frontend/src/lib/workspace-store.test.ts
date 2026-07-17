import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspace } from "./workspace-store";

function reset() {
  useWorkspace.setState({
    tabs: [],
    activeTabId: null,
    activeTab1: null,
    split: false,
    paneOf: {},
    focusedPane: 0,
  });
}

describe("openTab: navigate current tab vs open new tab", () => {
  beforeEach(reset);

  it("opens a first tab when nothing is active", () => {
    useWorkspace.getState().openTab("page", "a", "A", { newTab: false });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0]).toMatchObject({ kind: "page", refId: "a", title: "A" });
    expect(s.activeTabId).toBe(s.tabs[0].id);
  });

  it("a plain navigation click REPLACES the active tab in place", () => {
    const st = useWorkspace.getState();
    st.openTab("page", "a", "A", { newTab: false });
    const firstId = useWorkspace.getState().tabs[0].id;
    useWorkspace.getState().openTab("file", "b", "B", { newTab: false });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(1); // no new tab
    expect(s.tabs[0].id).toBe(firstId); // same tab id…
    expect(s.tabs[0]).toMatchObject({ kind: "file", refId: "b", title: "B" }); // …new content
  });

  it("cmd/ctrl-click (newTab:true) opens a second tab", () => {
    useWorkspace.getState().openTab("page", "a", "A", { newTab: false });
    useWorkspace.getState().openTab("file", "b", "B", { newTab: true });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(2);
    expect(s.activeTabId).toBe(s.tabs[1].id);
  });

  it("default (no opts) keeps opening new tabs — deep-links / new chat", () => {
    useWorkspace.getState().openTab("page", "a", "A");
    useWorkspace.getState().openTab("file", "b", "B");
    expect(useWorkspace.getState().tabs).toHaveLength(2);
  });

  it("reopening an already-open target focuses it instead of duplicating", () => {
    useWorkspace.getState().openTab("page", "a", "A", { newTab: true });
    useWorkspace.getState().openTab("file", "b", "B", { newTab: true });
    const firstId = useWorkspace.getState().tabs[0].id;
    useWorkspace.getState().openTab("page", "a", "A", { newTab: false });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(2); // no dup, no replace
    expect(s.activeTabId).toBe(firstId);
  });
});
