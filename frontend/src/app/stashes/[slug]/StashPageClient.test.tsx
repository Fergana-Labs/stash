import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashPageClient from "./StashPageClient";
import {
  getActivityTimeline,
  getEmbeddingProjection,
  getPublicStash,
} from "../../../lib/api";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../../../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  getPublicStash: vi.fn(),
  updateStash: vi.fn(),
  uploadFile: vi.fn(),
  getActivityTimeline: vi.fn(),
  getEmbeddingProjection: vi.fn(),
}));

vi.mock("../../../components/viz/AgentActivityTimeline", () => ({
  default: () => null,
}));
vi.mock("../../../components/viz/EmbeddingSpaceExplorer", () => ({
  default: () => null,
}));

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: null, loading: false, logout: vi.fn() }),
}));

vi.mock("./AddToWorkspaceButton", () => ({
  default: () => <button type="button">Add to workspace</button>,
}));

describe("StashPageClient sharing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, "", "/stashes/shared-stash");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(getActivityTimeline).mockResolvedValue({
      agents: [],
      buckets: [],
    });
    vi.mocked(getEmbeddingProjection).mockResolvedValue({
      points: [],
      stats: { total_embeddings: 0, projected: 0 },
      cached: false,
    });
    vi.mocked(getPublicStash).mockResolvedValue({
      stash: {
        id: "stash-1",
        workspace_id: "workspace-1",
        slug: "shared-stash",
        title: "Shared Stash",
        description: "",
        owner_id: "user-1",
        access: "public",
        discoverable: false,
        cover_image_url: null,
        icon_url: null,
        view_count: 0,
        items: [],
        is_external: false,
        added_to_workspace_id: null,
        forked_from_stash_id: null,
        created_at: "2026-05-11T00:00:00Z",
        updated_at: "2026-05-11T00:00:00Z",
      },
      workspace_name: "Demo Workspace",
      items: [],
      can_write: false,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("Share button opens a popover with a copy-link affordance", async () => {
    render(<StashPageClient slug="shared-stash" />);

    fireEvent.click(await screen.findByRole("button", { name: /Share/ }));
    // Popover renders a "Copy" button for the public URL; click it.
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/stashes/shared-stash`
      )
    );
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});
