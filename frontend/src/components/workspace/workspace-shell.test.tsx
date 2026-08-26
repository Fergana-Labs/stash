// A section route whose page.tsx isn't in rendersRouteContent silently shows
// the workbench instead of the page — the Tools/MCP page shipped dead this way
// (tests rendered the component directly, the shell never did). This locks the
// route → content mapping so a new management page failing to register fails a
// test instead of failing in prod.
import { beforeEach, describe, expect, it } from "vitest";
import { rendersRouteContent } from "./workspace-shell";
import { WORKBENCH_TAB_KINDS, urlForTab, hasPermanentUrl } from "@/lib/workspace-routes";
import { useWorkspace, type WorkbenchTab } from "@/lib/workspace-store";

describe("rendersRouteContent", () => {
  it("renders management pages beside the explorer", () => {
    expect(rendersRouteContent("/tools", null, null)).toBe(true);
    expect(rendersRouteContent("/sessions", null, null)).toBe(true);
    expect(rendersRouteContent("/skills", null, null)).toBe(true);
    expect(rendersRouteContent("/files", null, null)).toBe(true);
  });

  it("home is a full-page route, not a management page", () => {
    expect(rendersRouteContent("/", null, null)).toBe(false);
  });

  it("workbench sections do not render route content", () => {
    // An opened skill is a tab, not the launcher.
    expect(rendersRouteContent("/skills/folder/abc", null, null)).toBe(false);
  });

  it("an explicit explorer section always wins", () => {
    expect(rendersRouteContent("/tools", "files", null)).toBe(false);
    expect(rendersRouteContent("/sessions", "skills", null)).toBe(false);
  });

  it("sessions workspace view keeps the workbench", () => {
    expect(rendersRouteContent("/sessions", null, "1")).toBe(false);
  });
});

// The workbench pushes urlForTab on every tab click, and the shell decides off
// that URL whether to draw the workbench at all. A tab kind whose URL is a
// full page is therefore a tab you can never click back into — clicking it
// replaces the strip with that page — so the two rules below have to agree.
describe("tabs the workbench can host", () => {
  it("every hostable kind's URL still lands on the workbench", () => {
    for (const kind of WORKBENCH_TAB_KINDS) {
      // `tool` with the legacy "integrations" refId routes to the /tools
      // management page, so give every kind a content-shaped refId.
      const [path, query] = urlForTab({ kind, refId: "abc" }).split("?");
      const workspaceParam = new URLSearchParams(query).get("workspace");
      expect([kind, rendersRouteContent(path, null, workspaceParam)]).toEqual([kind, false]);
    }
  });

  it("kinds with no route at all refuse to invent one", () => {
    expect(() => urlForTab({ kind: "terminal", refId: "terminal" })).toThrow();
    expect(() => urlForTab({ kind: "machine-file", refId: "notes.md" })).toThrow();
  });

  // The explorer's VM section still opens these, and the workbench refocuses
  // them. Both ask hasPermanentUrl first, so the throw above stays a
  // programmer-error guard instead of a crash on a real click.
  it("marks the kinds that throw as having no permanent URL", () => {
    for (const kind of ["terminal", "machine-file"] as const) {
      expect(hasPermanentUrl(kind)).toBe(false);
      expect(() => urlForTab({ kind, refId: "x" })).toThrow();
    }
    for (const kind of WORKBENCH_TAB_KINDS) {
      expect(hasPermanentUrl(kind)).toBe(true);
    }
  });
});

// Users who had tabs open before chat was removed hydrate that state on their
// next visit. A persisted "agent" (chat) tab is a kind the workbench no longer
// knows, so hydrate carries the layout forward without those tabs rather than
// leaving the user to find the wreck.
describe("hydrate migrates persisted tabs of removed kinds", () => {
  beforeEach(() => {
    useWorkspace.setState({ tabs: [], activeTabId: null, activeTab1: null, split: false, paneOf: {}, focusedPane: 0 });
  });

  it("drops chat tabs and keeps the content tabs beside them", () => {
    // localStorage from before the chat removal still holds kind "agent" —
    // the string survives even though the TabKind type no longer has it.
    const chatTab = { id: "t1", kind: "agent", refId: "agent-abc" } as unknown as WorkbenchTab;
    useWorkspace.getState().hydrate({
      tabs: [chatTab, { id: "t2", kind: "page", refId: "p1" }],
      paneOf: { t1: 0, t2: 0 },
      activeTabId: "t1",
    });

    const s = useWorkspace.getState();
    expect(s.tabs).toEqual([{ id: "t2", kind: "page", refId: "p1" }]);
    expect(s.paneOf).toEqual({ t2: 0 });
    // The dropped tab was the active one — the strip must not point at a ghost.
    expect(s.activeTabId).toBe("t2");
  });

  it("closes the split when its only tab was an unhostable tab", () => {
    useWorkspace.getState().hydrate({
      tabs: [
        { id: "t1", kind: "page", refId: "p1" },
        { id: "t2", kind: "terminal", refId: "terminal" },
      ],
      paneOf: { t1: 0, t2: 1 },
      activeTabId: "t1",
      activeTab1: "t2",
      split: true,
      focusedPane: 1,
    });

    const s = useWorkspace.getState();
    expect(s.split).toBe(false);
    expect(s.activeTab1).toBeNull();
    expect(s.focusedPane).toBe(0);
  });

  it("leaves state that needs no migration untouched", () => {
    useWorkspace.getState().hydrate({
      tabs: [{ id: "t1", kind: "page", refId: "p1" }],
      paneOf: { t1: 0 },
      activeTabId: "t1",
    });

    expect(useWorkspace.getState().tabs).toHaveLength(1);
    expect(useWorkspace.getState().activeTabId).toBe("t1");
  });
});
