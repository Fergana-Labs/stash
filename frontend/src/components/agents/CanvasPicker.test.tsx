import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CanvasPicker from "./CanvasPicker";
import { listCanvases } from "@/lib/api";

vi.mock("@/lib/api", () => ({ listCanvases: vi.fn() }));

const canvas = {
  id: "cv-1",
  workspace_id: "ws-1",
  session_id: null,
  title: "Sales dashboard",
  blocks: [],
  created_by: "u-1",
  updated_by: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

describe("CanvasPicker", () => {
  beforeEach(() => {
    vi.mocked(listCanvases).mockResolvedValue({ canvases: [canvas] });
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("lists saved canvases and reopens the chosen one", async () => {
    const onSelect = vi.fn();
    render(<CanvasPicker workspaceId="ws-1" onSelect={onSelect} />);

    // Lazily loads only when opened.
    expect(listCanvases).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Canvases"));

    await waitFor(() => expect(screen.getByText("Sales dashboard")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Sales dashboard"));
    expect(onSelect).toHaveBeenCalledWith("cv-1");
  });
});
