import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CartridgePageClient from "./CartridgePageClient";
import {
  ShellChromeProvider,
  useShellChromeValue,
} from "../../../../components/ShellChromeContext";
import {
  addCartridgeMember,
  getActivityTimeline,
  getEmbeddingProjection,
  getMe,
  getPublicCartridge,
  listCartridgeMembers,
  searchUsers,
  updateCartridge,
  type PublicCartridgeDetail,
} from "../../../../lib/api";

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

vi.mock("../../../../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  addExternalCartridge: vi.fn(),
  addCartridgeMember: vi.fn(),
  createPage: vi.fn(),
  getMe: vi.fn(),
  getPublicCartridge: vi.fn(),
  listAllPages: vi.fn(),
  listAllTables: vi.fn(),
  listFiles: vi.fn(),
  listMySessions: vi.fn(),
  listCartridgeMembers: vi.fn(),
  removeCartridgeMember: vi.fn(),
  searchUsers: vi.fn(),
  updateCartridge: vi.fn(),
  uploadFile: vi.fn(),
  getActivityTimeline: vi.fn(),
  getEmbeddingProjection: vi.fn(),
  // Tests render the authenticated view of the page; pretend the
  // viewer has a token so insight panels mount as before.
  getToken: vi.fn(() => "test-token"),
}));

vi.mock("../../../../components/viz/ContributorActivityTimeline", () => ({
  default: () => null,
}));
vi.mock("../../../../components/viz/EmbeddingSpaceExplorer", () => ({
  default: () => null,
}));

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: authState.user, loading: false, logout: vi.fn() }),
}));

vi.mock("./AddToWorkspaceButton", () => ({
  default: () => <button type="button">Add to my files</button>,
}));

// Mirrors how AppShell consumes the ShellChromeContext: pulls the page-
// registered shareAction out of context and renders it under a <header>.
// Lets us assert that share buttons surface in the app chrome.
function ShellChromeHarness({ children }: { children: ReactNode }) {
  return (
    <ShellChromeProvider>
      <SharedHeader />
      <main>{children}</main>
    </ShellChromeProvider>
  );
}

function SharedHeader() {
  const { shareAction } = useShellChromeValue();
  return <header>{shareAction}</header>;
}

function renderCartridge(ui: ReactNode) {
  return render(ui, { wrapper: ShellChromeHarness });
}

function stashDetail(
  stash: Partial<PublicCartridgeDetail["stash"]> = {},
): PublicCartridgeDetail {
  return {
    stash: {
      id: "stash-1",
      workspace_id: "workspace-1",
      slug: "shared-stash",
      title: "Shared Stash",
      description: "",
      owner_id: "user-1",
      owner_name: "henry",
      owner_display_name: "Henry",
      access: "public",
      workspace_permission: "read",
      public_permission: "read",
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
  };
}

describe("CartridgePageClient sharing", () => {
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
    window.history.pushState({}, "", "/cartridges/shared-stash");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(getActivityTimeline).mockResolvedValue({
      contributors: [],
      buckets: [],
    });
    vi.mocked(getEmbeddingProjection).mockResolvedValue({
      points: [],
      stats: { total_embeddings: 0, projected: 0 },
      cached: false,
    });
    vi.mocked(getMe).mockResolvedValue(authState.user!);
    vi.mocked(getPublicCartridge).mockResolvedValue(stashDetail());
    vi.mocked(listCartridgeMembers).mockResolvedValue([
      {
        user_id: "user-2",
        name: "sam",
        display_name: "Sam",
        permission: "write",
        granted_by: "user-1",
        created_at: "2026-05-12T00:00:00Z",
      },
    ]);
    vi.mocked(searchUsers).mockResolvedValue([
      { id: "user-3", name: "alex", display_name: "Alex" },
    ]);
    vi.mocked(updateCartridge).mockImplementation(async (_stashId, updates) => ({
      ...stashDetail().stash,
      ...updates,
    }));
    vi.mocked(addCartridgeMember).mockResolvedValue({
      user_id: "user-3",
      name: "alex",
      display_name: "Alex",
      permission: "read",
      granted_by: "user-1",
      created_at: "2026-05-13T00:00:00Z",
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the Share button in the app header with a copy-link affordance", async () => {
    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    const shareButton = await screen.findByRole("button", { name: "Share" });
    expect(
      screen.getByRole("button", { name: "Copy agent handoff link" }),
    ).toBeInTheDocument();
    expect(shareButton.closest("header")).not.toBeNull();
    expect(screen.getAllByRole("button", { name: "Share" })).toHaveLength(1);

    fireEvent.click(shareButton);
    // Popover renders a "Copy" button for the public URL; click it.
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/cartridges/shared-stash`,
      ),
    );
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("copies an agent-readable handoff link from the app header", async () => {
    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    const handoffButton = await screen.findByRole("button", {
      name: "Copy agent handoff link",
    });
    fireEvent.click(handoffButton);

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/api/v1/cartridges/shared-stash?format=text`,
      ),
    );
    expect(
      screen.getByRole("button", { name: "Copy agent handoff link" }),
    ).toHaveTextContent("Copied");
  });

  it("makes private Cartridges public and unlisted before copying an agent link", async () => {
    vi.mocked(getPublicCartridge).mockResolvedValueOnce({
      ...stashDetail({
        access: "private",
        workspace_permission: "none",
        public_permission: "none",
        discoverable: false,
      }),
      can_write: true,
    });

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Copy agent handoff link" }),
    );

    await waitFor(() =>
      expect(updateCartridge).toHaveBeenCalledWith("stash-1", {
        workspace_permission: "read",
        public_permission: "read",
        discoverable: false,
      }),
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      `${window.location.origin}/api/v1/cartridges/shared-stash?format=text`,
    );
    expect(
      screen.getByRole("button", { name: "Copy agent handoff link" }),
    ).toHaveTextContent("Copied");
  });

  it("can make the Stash private from the Share dropdown", async () => {
    vi.mocked(getPublicCartridge).mockResolvedValueOnce({
      ...stashDetail({
        access: "public",
        workspace_permission: "write",
        public_permission: "read",
      }),
      can_write: true,
    });

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Share Shared Stash",
    });
    fireEvent.change(within(dialog).getByLabelText("Visibility"), {
      target: { value: "private" },
    });

    await waitFor(() =>
      expect(updateCartridge).toHaveBeenCalledWith("stash-1", {
        workspace_permission: "none",
        public_permission: "none",
        discoverable: false,
      }),
    );
  });

  it("manages explicit Stash members from the Share dropdown", async () => {
    vi.mocked(getPublicCartridge).mockResolvedValueOnce({
      ...stashDetail({
        access: "private",
        workspace_permission: "none",
        public_permission: "none",
      }),
      can_write: true,
    });

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Share Shared Stash",
    });

    expect(await within(dialog).findByText("@sam")).toBeInTheDocument();
    expect(listCartridgeMembers).toHaveBeenCalledWith("stash-1");

    fireEvent.change(within(dialog).getByPlaceholderText("Search users"), {
      target: { value: "alex" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Search" }));
    fireEvent.click(await within(dialog).findByRole("button", { name: /Alex/ }));

    await waitFor(() =>
      expect(addCartridgeMember).toHaveBeenCalledWith("stash-1", "user-3", "read"),
    );
  });

  it("keeps add/create flows behind the single Add things button", async () => {
    vi.mocked(getPublicCartridge).mockResolvedValueOnce({
      ...stashDetail({
        access: "workspace",
        workspace_permission: "read",
        public_permission: "none",
      }),
      can_write: true,
    });

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    expect(
      await screen.findByRole("button", { name: "+ Add things" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Stash settings" })).toHaveAttribute(
      "href",
      "/cartridges/shared-stash/settings",
    );
    expect(
      screen.queryByPlaceholderText(
        "Paste a link, type a note, or drop a file",
      ),
    ).not.toBeInTheDocument();
  });

  it("does not render stash access as a title badge", async () => {
    vi.mocked(getPublicCartridge).mockResolvedValueOnce(
      stashDetail({
        access: "workspace",
        workspace_permission: "read",
        public_permission: "none",
      }),
    );

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    const title = await screen.findByRole("heading", { name: "Shared Stash" });

    expect(title).toHaveTextContent("Shared Stash");
    expect(title).not.toHaveTextContent("workspace");
  });

  it("loads only recent activity for the commit graph", async () => {
    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    expect(
      await screen.findByText("Activity in this cartridge — last 30 days"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(getActivityTimeline).toHaveBeenCalledWith(
        30,
        "day",
        undefined,
        "stash-1",
      ),
    );
  });

  it("shows the stash author in the detail header", async () => {
    vi.mocked(getPublicCartridge).mockResolvedValueOnce(
      stashDetail({ owner_name: "sam", owner_display_name: "Sam" })
    );

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    expect(await screen.findByText("by Sam")).toBeInTheDocument();
  });

  it("opens single-file cartridges directly on the file preview", async () => {
    // The primary-item shortcut only fires for a stash with exactly one
    // item. A folder wrapper means "open container" — could grow — so we
    // render bundle chrome for it. This test pins the strict shape.
    const detail = stashDetail({
      description: "<p>One screenshot.</p>",
    });
    detail.items = [
      {
        object_type: "file",
        object_id: "file-1",
        position: 0,
        label: "shot.png",
        inline: {
          name: "shot.png",
          content_type: "image/png",
          size_bytes: 1234,
          url: "https://files.test/shot.png",
        },
      },
    ];
    vi.mocked(getPublicCartridge).mockResolvedValueOnce(detail);

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    const image = await screen.findByRole("img", { name: "shot.png" });
    expect(image).toHaveAttribute("src", "https://files.test/shot.png");
    expect(screen.getByText("1 item")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Files" })).not.toBeInTheDocument();
    expect(getActivityTimeline).not.toHaveBeenCalled();
    expect(getEmbeddingProjection).not.toHaveBeenCalled();
  });

  it("shows bundle chrome for a file-plus-folder stash (no primary shortcut)", async () => {
    // The folder is an open container — adding more items would invalidate
    // any "this cartridge IS the file" promise — so we render the bundle list
    // and the viz section, not the file preview.
    const detail = stashDetail({
      description: "<p>Uploaded from shot.png</p>",
    });
    detail.items = [
      {
        object_type: "folder",
        object_id: "folder-1",
        position: 0,
        label: "shot",
        inline: { pages: [], files: [] },
      },
      {
        object_type: "file",
        object_id: "file-1",
        position: 1,
        label: "shot.png",
        inline: {
          name: "shot.png",
          content_type: "image/png",
          size_bytes: 1234,
          url: "https://files.test/shot.png",
        },
      },
    ];
    vi.mocked(getPublicCartridge).mockResolvedValueOnce(detail);

    renderCartridge(<CartridgePageClient slug="shared-stash" />);

    expect(await screen.findByText("2 items")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Files" })).toBeInTheDocument();
  });
});
