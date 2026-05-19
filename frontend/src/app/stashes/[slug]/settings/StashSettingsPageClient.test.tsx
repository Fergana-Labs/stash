import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashSettingsPageClient from "./StashSettingsPageClient";
import {
  addStashMember,
  getPublicStash,
  listStashMembers,
  searchUsers,
  updateStash,
  type PublicStashDetail,
} from "../../../../lib/api";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

const authState = vi.hoisted(() => ({
  user: {
    id: "user-1",
    name: "henry",
    display_name: "Henry",
    description: "",
    created_at: "2026-05-11T00:00:00Z",
    last_seen: "2026-05-11T00:00:00Z",
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

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("../../../../components/AppShell", () => ({
  default: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

vi.mock("../../../../components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: authState.user,
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("../../../../lib/stashNavigationCache", () => ({
  resetStashNavigationCache: vi.fn(),
}));

vi.mock("../../../../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  addStashMember: vi.fn(),
  deleteStash: vi.fn(),
  getPublicStash: vi.fn(),
  listStashMembers: vi.fn(),
  removeStashMember: vi.fn(),
  searchUsers: vi.fn(),
  updateStash: vi.fn(),
  uploadFile: vi.fn(),
}));

function stashDetail(
  stash: Partial<PublicStashDetail["stash"]> = {},
): PublicStashDetail {
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
    can_write: true,
  };
}

describe("StashSettingsPageClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPublicStash).mockResolvedValue(stashDetail());
    vi.mocked(listStashMembers).mockResolvedValue([
      {
        user_id: "user-2",
        name: "sam",
        display_name: "Sam",
        permission: "write",
        granted_by: "user-1",
        created_at: "2026-05-12T00:00:00Z",
      },
    ]);
    vi.mocked(updateStash).mockImplementation(async (_stashId, updates) => ({
      ...stashDetail().stash,
      ...updates,
    }));
    vi.mocked(searchUsers).mockResolvedValue([
      { id: "user-3", name: "alex", display_name: "Alex" },
    ]);
    vi.mocked(addStashMember).mockResolvedValue({
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

  it("loads editable stash settings and explicit members", async () => {
    render(<StashSettingsPageClient slug="shared-stash" />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Shared Stash")).toBeInTheDocument();
    expect(screen.getByText("@henry")).toBeInTheDocument();
    expect(screen.getByText("@sam")).toBeInTheDocument();
    expect(listStashMembers).toHaveBeenCalledWith("stash-1");
  });

  it("saves title and visibility changes", async () => {
    render(<StashSettingsPageClient slug="shared-stash" />);

    fireEvent.change(await screen.findByLabelText("Title"), {
      target: { value: "Better Stash" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateStash).toHaveBeenCalledWith("stash-1", {
        title: "Better Stash",
        access: "public",
        discoverable: false,
      }),
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("searches and adds a member", async () => {
    render(<StashSettingsPageClient slug="shared-stash" />);

    fireEvent.change(await screen.findByPlaceholderText("Search users"), {
      target: { value: "alex" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    const addResult = await screen.findByRole("button", { name: /Alex/ });
    fireEvent.click(addResult);

    await waitFor(() =>
      expect(addStashMember).toHaveBeenCalledWith("stash-1", "user-3", "read"),
    );
  });
});
