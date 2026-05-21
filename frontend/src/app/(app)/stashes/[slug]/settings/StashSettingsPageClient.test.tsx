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
  getPublicStash,
  updateStash,
  type PublicStashDetail,
} from "../../../../../lib/api";

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

vi.mock("../../../../../components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("../../../../../components/ShellChromeContext", () => ({
  useActiveWorkspaceId: vi.fn(),
}));

vi.mock("../../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: authState.user,
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("../../../../../lib/stashNavigationCache", () => ({
  resetStashNavigationCache: vi.fn(),
}));

vi.mock("../../../../../lib/api", () => ({
  deleteStash: vi.fn(),
  getPublicStash: vi.fn(),
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
      workspace_permission: "view",
      public_permission: "view",
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
    can_comment: true,
    can_edit: true,
    can_manage: true,
  };
}

describe("StashSettingsPageClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPublicStash).mockResolvedValue(stashDetail());
    vi.mocked(updateStash).mockImplementation(async (_stashId, updates) => ({
      ...stashDetail().stash,
      ...updates,
    }));
  });

  afterEach(() => {
    cleanup();
  });

  it("loads editable stash settings", async () => {
    render(<StashSettingsPageClient slug="shared-stash" />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Shared Stash")).toBeInTheDocument();
    expect(screen.queryByText("Members")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Visibility")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace access")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Public access")).not.toBeInTheDocument();
    expect(screen.queryByText("List on Discover")).not.toBeInTheDocument();
  });

  it("saves title changes only", async () => {
    render(<StashSettingsPageClient slug="shared-stash" />);

    fireEvent.change(await screen.findByLabelText("Title"), {
      target: { value: "Better Stash" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateStash).toHaveBeenCalledWith("stash-1", {
        title: "Better Stash",
      }),
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });
});
