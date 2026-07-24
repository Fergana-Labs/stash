// A section route whose page.tsx isn't in rendersRouteContent silently shows
// the workbench instead of the page — the Tools/MCP page shipped dead this way
// (tests rendered the component directly, the shell never did). This locks the
// route → content mapping so a new management page failing to register fails a
// test instead of failing in prod.
import { describe, expect, it } from "vitest";
import { rendersRouteContent } from "./workspace-shell";

describe("rendersRouteContent", () => {
  it("renders management pages beside the explorer", () => {
    expect(rendersRouteContent("/tools", null, null)).toBe(true);
    expect(rendersRouteContent("/sessions", null, null)).toBe(true);
    expect(rendersRouteContent("/memory", null, null)).toBe(true);
    expect(rendersRouteContent("/memory/wiki", null, null)).toBe(true);
  });

  it("workbench sections do not render route content", () => {
    expect(rendersRouteContent("/files", null, null)).toBe(false);
    expect(rendersRouteContent("/skills", null, null)).toBe(false);
    expect(rendersRouteContent("/agents", null, null)).toBe(false);
  });

  it("an explicit explorer section always wins", () => {
    expect(rendersRouteContent("/tools", "files", null)).toBe(false);
    expect(rendersRouteContent("/sessions", "skills", null)).toBe(false);
  });

  it("sessions workspace view keeps the workbench", () => {
    expect(rendersRouteContent("/sessions", null, "1")).toBe(false);
  });
});
