import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItemsList from "./ItemsList";
import type { GridItem } from "./FolderItemGrid";

const item: GridItem = {
  kind: "html",
  id: "page-1",
  name: "Stash Product Memo 6.1.25",
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
