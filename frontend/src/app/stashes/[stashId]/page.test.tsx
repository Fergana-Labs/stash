import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashHomePage from "./page";
import {
  getStashSpine,
  getWorkspace,
  getWorkspaceMembers,
  updateWorkspace,
} from "../../../lib/api";
import type { HomeBackground, Workspace } from "../../../lib/types";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ stashId: "ws-1" }),
  useRouter: () => ({ push: nav.push }),
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
  default: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

vi.mock("../../../components/MembersModal", () => ({
  default: () => null,
}));

vi.mock("../../../components/StashQuickAdd", () => ({
  default: () => null,
}));

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user,
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("../../../lib/api", () => ({
  createFolder: vi.fn(),
  createPage: vi.fn(),
  getStashSpine: vi.fn(),
  getWorkspace: vi.fn(),
  getWorkspaceMembers: vi.fn(),
  joinWorkspace: vi.fn(),
  updateWorkspace: vi.fn(),
  uploadFile: vi.fn(),
}));

const defaultBackground: HomeBackground = {
  kind: "gradient",
  gradient_start: "#FED7AA",
  gradient_middle: "#FEF3C7",
  gradient_end: "#FFE4E6",
  image_url: null,
};

const user = {
  id: "user-1",
  name: "Henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-05-11T00:00:00Z",
  last_seen: "2026-05-11T00:00:00Z",
};

function workspace(home_background: HomeBackground = defaultBackground): Workspace {
  return {
    id: "ws-1",
    name: "Demo Stash",
    description: "",
    creator_id: "user-1",
    invite_code: "invite",
    is_public: true,
    created_at: "2026-05-11T00:00:00Z",
    updated_at: "2026-05-11T00:00:00Z",
    member_count: 1,
    home_background,
  };
}

const members = [
  {
    user_id: "user-1",
    name: "Henry",
    display_name: "Henry",
    role: "owner",
    joined_at: "2026-05-11T00:00:00Z",
  },
];

const emptySpine = {
  sessions: [],
  wiki: {
    folders: [],
    pages: [],
    files: [],
  },
};

function backgroundElement() {
  const element = document.querySelector("[style*='linear-gradient']");
  if (!element) throw new Error("Missing rendered background");
  return element;
}

describe("Stash homepage background customization", () => {
  beforeEach(() => {
    nav.push.mockClear();
    vi.clearAllMocks();
    vi.mocked(getWorkspace).mockResolvedValue(workspace());
    vi.mocked(getWorkspaceMembers).mockResolvedValue(members);
    vi.mocked(getStashSpine).mockResolvedValue(emptySpine);
    vi.mocked(updateWorkspace).mockImplementation(async (_workspaceId, data) => {
      return workspace(data.home_background ?? defaultBackground);
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("saves a gradient background and renders it after reload", async () => {
    const { unmount } = render(<StashHomePage />);

    await screen.findByText("Demo Stash");
    fireEvent.click(screen.getByRole("button", { name: "Customize background" }));
    fireEvent.change(screen.getByDisplayValue("#FED7AA"), {
      target: { value: "#112233" },
    });
    fireEvent.change(screen.getByDisplayValue("#FEF3C7"), {
      target: { value: "#445566" },
    });
    fireEvent.change(screen.getByDisplayValue("#FFE4E6"), {
      target: { value: "#778899" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(updateWorkspace).toHaveBeenCalledWith("ws-1", {
        home_background: {
          kind: "gradient",
          gradient_start: "#112233",
          gradient_middle: "#445566",
          gradient_end: "#778899",
          image_url: null,
        },
      })
    );
    expect(backgroundElement().getAttribute("style")).toContain("rgb(17, 34, 51)");

    unmount();
    vi.mocked(getWorkspace).mockResolvedValue(
      workspace({
        kind: "gradient",
        gradient_start: "#112233",
        gradient_middle: "#445566",
        gradient_end: "#778899",
        image_url: null,
      })
    );
    render(<StashHomePage />);

    await screen.findByText("Demo Stash");
    expect(backgroundElement().getAttribute("style")).toContain("rgb(119, 136, 153)");
  });

  it("saves an image URL background", async () => {
    render(<StashHomePage />);

    await screen.findByText("Demo Stash");
    fireEvent.click(screen.getByRole("button", { name: "Customize background" }));
    fireEvent.click(screen.getByRole("button", { name: "Image" }));
    fireEvent.change(screen.getByPlaceholderText("https://example.com/cover.jpg"), {
      target: { value: "https://example.com/banner.jpg" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(updateWorkspace).toHaveBeenCalledWith("ws-1", {
        home_background: {
          kind: "image",
          gradient_start: "#FED7AA",
          gradient_middle: "#FEF3C7",
          gradient_end: "#FFE4E6",
          image_url: "https://example.com/banner.jpg",
        },
      })
    );
    expect(backgroundElement().getAttribute("style")).toContain(
      "https://example.com/banner.jpg"
    );
  });
});
