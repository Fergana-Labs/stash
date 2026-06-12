import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItemsList from "./ItemsList";
import type { GridItem } from "./kind";

const item: GridItem = {
  kind: "html",
  id: "page-1",
  name: "Skill Product Memo 6.1.25",
  subtitle: "html page",
  updatedAt: "2026-06-02T21:35:23Z",
};

function renderList(onNavigate = vi.fn()) {
  render(
    <ItemsList
      items={[item]}
      onNavigate={onNavigate}
      onReparent={vi.fn()}
      onReparentMany={vi.fn()}
      onDelete={vi.fn()}
      isPinned={() => false}
      onTogglePin={vi.fn()}
      selectedIds={new Set()}
      onToggleSelect={vi.fn()}
      selectedDragPayloads={[]}
    />
  );
  return onNavigate;
}

function rowFor(name: string): HTMLElement {
  const row = screen.getByText(name).closest('[role="button"]');
  if (!row) throw new Error(`No row for ${name}`);
  return row as HTMLElement;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ItemsList type filter", () => {
  const png: GridItem = {
    kind: "file",
    id: "file-1",
    name: "screenshot.png",
    subtitle: "file",
    contentType: "image/png",
    updatedAt: "2026-06-03T10:00:00Z",
  };

  function renderMixedList() {
    render(
      <ItemsList
        items={[item, png]}
        onNavigate={vi.fn()}
        onReparent={vi.fn()}
        onReparentMany={vi.fn()}
        onDelete={vi.fn()}
        isPinned={() => false}
        onTogglePin={vi.fn()}
        selectedIds={new Set()}
        onToggleSelect={vi.fn()}
        selectedDragPayloads={[]}
      />
    );
  }

  it("narrows the list to the chosen type", () => {
    renderMixedList();

    fireEvent.click(screen.getByRole("button", { name: /^Type$/i }));
    fireEvent.click(screen.getByRole("button", { name: "PNG" }));

    expect(screen.getByText(png.name)).toBeDefined();
    expect(screen.queryByText(item.name)).toBeNull();
  });

  it("restores all rows via All types", () => {
    renderMixedList();

    fireEvent.click(screen.getByRole("button", { name: /^Type$/i }));
    fireEvent.click(screen.getByRole("button", { name: "PNG" }));
    fireEvent.click(screen.getByRole("button", { name: /^Type: PNG$/i }));
    fireEvent.click(screen.getByRole("button", { name: "All types" }));

    expect(screen.getByText(item.name)).toBeDefined();
    expect(screen.getByText(png.name)).toBeDefined();
  });
});

describe("ItemsList navigation", () => {
  it("opens list rows in a new tab on command-click", () => {
    const onNavigate = renderList();

    fireEvent.click(rowFor(item.name), { metaKey: true });

    expect(onNavigate).toHaveBeenCalledWith(item, { newTab: true });
  });

  it("keeps normal list row clicks in the current tab", () => {
    const onNavigate = renderList();

    fireEvent.click(rowFor(item.name));

    expect(onNavigate).toHaveBeenCalledWith(item, { newTab: false });
  });
});
