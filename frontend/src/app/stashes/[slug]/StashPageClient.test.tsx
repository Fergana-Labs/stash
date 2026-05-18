import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashPageClient from "./StashPageClient";
import {
  getActivityTimeline,
  getEmbeddingProjection,
  getPublicStash,
  type PublicStashDetail,
} from "../../../lib/api";

const authState = vi.hoisted(() => ({
  user: null as null | {
    id: string;
    name: string;
    display_name: string;
    description: string;
    created_at: string;
    last_seen: string;
  },
}));

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

vi.mock("../../../components/AppShell", () => ({
  default: ({
    children,
    shareAction,
  }: {
    children: ReactNode;
    shareAction?: ReactNode;
  }) => (
    <>
      <header>{shareAction}</header>
      <main>{children}</main>
    </>
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
  addExternalStash: vi.fn(),
  createPage: vi.fn(),
  getPublicStash: vi.fn(),
  getStashShare: vi.fn(),
  listAllPages: vi.fn(),
  listAllTables: vi.fn(),
  listFiles: vi.fn(),
  listMySessions: vi.fn(),
  updateStash: vi.fn(),
  updateStashShare: vi.fn(),
  uploadFile: vi.fn(),
  searchUsers: vi.fn(),
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
  useAuth: () => ({ user: authState.user, loading: false, logout: vi.fn() }),
}));

vi.mock("./AddToWorkspaceButton", () => ({
  default: () => <button type="button">Add to workspace</button>,
}));

function stashDetail(
  stash: Partial<PublicStashDetail["stash"]> = {}
): PublicStashDetail {
  return {
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
      ...stash,
    },
    workspace_name: "Demo Workspace",
    items: [],
    can_write: false,
    can_manage_access: false,
  };
}

describe("StashPageClient sharing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = {
      id: "user-1",
      name: "Henry",
      display_name: "Henry",
      description: "",
      created_at: "2026-05-11T00:00:00Z",
      last_seen: "2026-05-11T00:00:00Z",
    };
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
    vi.mocked(getPublicStash).mockResolvedValue(stashDetail());
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the Share button in the app header with a copy-link affordance", async () => {
    render(<StashPageClient slug="shared-stash" />);

    const shareButton = await screen.findByRole("button", { name: "Share" });
    expect(shareButton.closest("header")).not.toBeNull();
    expect(screen.getAllByRole("button", { name: "Share" })).toHaveLength(1);

    fireEvent.click(shareButton);
    // The share sheet renders a "Copy" button for the Stash URL.
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/stashes/shared-stash`
      )
    );
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("keeps add/create flows behind the single Add things button", async () => {
    vi.mocked(getPublicStash).mockResolvedValueOnce({
      ...stashDetail({ access: "workspace" }),
      can_write: true,
    });

    render(<StashPageClient slug="shared-stash" />);

    expect(await screen.findByRole("button", { name: "+ Add things" })).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Paste a link, type a note, or drop a file")
    ).not.toBeInTheDocument();
  });

  it("does not render stash access as a title badge", async () => {
    vi.mocked(getPublicStash).mockResolvedValueOnce(
      stashDetail({ access: "workspace" })
    );

    render(<StashPageClient slug="shared-stash" />);

    const title = await screen.findByRole("heading", { name: "Shared Stash" });

    expect(title).toHaveTextContent("Shared Stash");
    expect(title).not.toHaveTextContent("workspace");
  });
});
