import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ItemsColumns from "./ItemsColumns";
import type { GridItem } from "./kind";

vi.mock("../../../lib/api", () => ({
  getFolderContents: vi.fn(),
}));

// Three root items deliberately out of every sort order so each sort produces a
// distinct, checkable sequence: name asc → Apple, Banana, Cherry; date desc →
// Cherry (newest), Apple, Banana; size desc → Banana (3kb), Cherry, Apple.
const ROOT_ITEMS: GridItem[] = [
  {
    kind: "file",
    id: "cherry",
    name: "Cherry",
    subtitle: "",
    sizeBytes: 2000,
    updatedAt: "2026-06-10T00:00:00Z",
  },
  {
    kind: "file",
    id: "apple",
    name: "Apple",
    subtitle: "",
    sizeBytes: 1000,
    updatedAt: "2026-06-01T00:00:00Z",
  },
  {
    kind: "file",
    id: "banana",
    name: "Banana",
    subtitle: "",
    sizeBytes: 3000,
    updatedAt: "2026-06-05T00:00:00Z",
  },
];

function renderColumns() {
  render(
    <ItemsColumns
      workspaceId="ws-1"
      rootItems={ROOT_ITEMS}
      onNavigate={vi.fn()}
      onReparent={vi.fn()}
    />,
  );
}

// The first (root) column is the only one rendered before any drill-down.
function columnNames(): string[] {
  const rows = screen.getAllByRole("button").filter((el) => {
    const name = el.textContent ?? "";
    return ["Apple", "Banana", "Cherry"].includes(name.trim());
  });
  return rows.map((el) => el.textContent?.trim() ?? "");
}

function chooseSort(label: string) {
  fireEvent.click(screen.getByRole("button", { name: /^Sort:/ }));
  // The active menu item carries a trailing direction arrow, so match the
  // label from the start rather than exactly.
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${label}`) }));
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ItemsColumns sorting", () => {
  it("defaults to alphabetical (Name A→Z) order", () => {
    renderColumns();
    expect(columnNames()).toEqual(["Apple", "Banana", "Cherry"]);
  });

  it("sorts chronologically newest-first when Date created is chosen", () => {
    renderColumns();
    chooseSort("Date created");
    expect(columnNames()).toEqual(["Cherry", "Banana", "Apple"]);
  });

  it("flips direction when the active key is chosen again", () => {
    renderColumns();
    chooseSort("Date created"); // newest first
    chooseSort("Date created"); // now oldest first
    expect(columnNames()).toEqual(["Apple", "Banana", "Cherry"]);
  });

  it("sorts by size largest-first when Size is chosen", () => {
    renderColumns();
    chooseSort("Size");
    expect(columnNames()).toEqual(["Banana", "Cherry", "Apple"]);
  });

  it("persists the chosen sort across remounts", () => {
    renderColumns();
    chooseSort("Date created");
    cleanup();
    renderColumns();
    expect(columnNames()).toEqual(["Cherry", "Banana", "Apple"]);
  });
});
