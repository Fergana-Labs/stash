import { beforeEach, describe, expect, it } from "vitest";

import { titleKey, useWorkspace } from "./workspace-store";

function reset() {
  useWorkspace.setState({
    tabs: [],
    activeTabId: null,
    activeTab1: null,
    split: false,
    paneOf: {},
    focusedPane: 0,
    titles: {},
  });
}

describe("openTab: navigate current tab vs open new tab", () => {
  beforeEach(reset);

  it("opens a first tab when nothing is active", () => {
    useWorkspace.getState().openTab("page", "a", { newTab: false, title: "A" });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0]).toMatchObject({ kind: "page", refId: "a" });
    expect(s.activeTabId).toBe(s.tabs[0].id);
  });

  it("a plain navigation click REPLACES the active tab in place", () => {
    const st = useWorkspace.getState();
    st.openTab("page", "a", { newTab: false, title: "A" });
    const firstId = useWorkspace.getState().tabs[0].id;
    useWorkspace.getState().openTab("file", "b", { newTab: false, title: "B" });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(1); // no new tab
    expect(s.tabs[0].id).toBe(firstId); // same tab id…
    expect(s.tabs[0]).toMatchObject({ kind: "file", refId: "b" }); // …new content
  });

  it("cmd/ctrl-click (newTab:true) opens a second tab", () => {
    useWorkspace.getState().openTab("page", "a", { newTab: false, title: "A" });
    useWorkspace.getState().openTab("file", "b", { newTab: true, title: "B" });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(2);
    expect(s.activeTabId).toBe(s.tabs[1].id);
  });

  it("default (no opts) keeps opening new tabs — deep-links / new chat", () => {
    useWorkspace.getState().openTab("page", "a");
    useWorkspace.getState().openTab("file", "b");
    expect(useWorkspace.getState().tabs).toHaveLength(2);
  });

  it("reopening an already-open target focuses it instead of duplicating", () => {
    useWorkspace.getState().openTab("page", "a", { newTab: true, title: "A" });
    useWorkspace.getState().openTab("file", "b", { newTab: true, title: "B" });
    const firstId = useWorkspace.getState().tabs[0].id;
    useWorkspace.getState().openTab("page", "a", { newTab: false });
    const s = useWorkspace.getState();
    expect(s.tabs).toHaveLength(2); // no dup, no replace
    expect(s.activeTabId).toBe(firstId);
  });
});

describe("tab titles: content-keyed, body-published", () => {
  beforeEach(reset);

  it("openTab without a title leaves the cache empty — no id-as-title", () => {
    // The deep-link path: only the content id is known at open time. The tab
    // must NOT be named after it; the body publishes the real name later.
    useWorkspace.getState().openTab("skill", "11346cd2", { newTab: false });
    const s = useWorkspace.getState();
    expect(s.titles[titleKey("skill", "11346cd2")]).toBeUndefined();
  });

  it("setTitle publishes the content's name for its tab", () => {
    useWorkspace.getState().openTab("skill", "11346cd2", { newTab: false });
    useWorkspace.getState().setTitle("skill", "11346cd2", "Brake Shoes");
    expect(useWorkspace.getState().titles[titleKey("skill", "11346cd2")]).toBe("Brake Shoes");
  });

  it("a body-published title overwrites the opener's seed (content wins)", () => {
    useWorkspace.getState().openTab("page", "a", { newTab: false, title: "stale name" });
    useWorkspace.getState().setTitle("page", "a", "fresh name");
    expect(useWorkspace.getState().titles[titleKey("page", "a")]).toBe("fresh name");
  });

  it("in-place navigation shows the new target's title, not the old tab's", () => {
    // Titles are keyed by content, not by tab id — replacing a tab's target
    // must never leave the old content's name on the strip.
    useWorkspace.getState().openTab("page", "a", { newTab: false, title: "A" });
    useWorkspace.getState().openTab("file", "b", { newTab: false, title: "B" });
    const s = useWorkspace.getState();
    expect(s.titles[titleKey("file", "b")]).toBe("B");
    expect(s.titles[titleKey("page", "a")]).toBe("A"); // still cached for its own content
  });
});
