import {
  cleanup,
  fireEvent,
  render as renderBase,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillsPage from "./page";
import { createSkill, listSkills, type Skill } from "@/lib/api";
import { ConfirmDialogProvider } from "@/components/ConfirmDialog";

function render(ui: ReactNode) {
  return renderBase(ui, { wrapper: ConfirmDialogProvider });
}

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
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

vi.mock("@/lib/api", () => ({
  API_BASE: "",
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  createSkill: vi.fn(),
  deleteFolder: vi.fn(),
  forkSkill: vi.fn(),
  listSkills: vi.fn(),
  // useAuth (mounted by the page) short-circuits to a signed-out state when
  // there's no token, so these never hit the network.
  getToken: vi.fn(() => null),
  getMe: vi.fn(),
  clearToken: vi.fn(),
  revokeStoredApiKey: vi.fn(),
}));

vi.mock("@/lib/pins", () => ({
  usePins: () => ({
    pinnedIds: [],
    pinnedSet: new Set<string>(),
    toggle: vi.fn(),
  }),
}));

vi.mock("@/lib/skillNavigationCache", () => ({
  refreshSidebar: vi.fn(() => Promise.resolve()),
}));

function skill(overrides: Partial<Skill> = {}): Skill {
  return {
    folder_id: "folder-1",
    name: "Launch Plan",
    description: "How we launch",
    when_to_use: "",
    version: "",
    mcp_exposed: false,
    file_count: 3,
    updated_at: "2026-06-01T00:00:00Z",
    published: null,
    ...overrides,
  };
}

describe("SkillsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    router.push.mockReset();
    vi.mocked(listSkills).mockResolvedValue([
      skill(),
      skill({
        folder_id: "folder-2",
        name: "Research",
        description: "",
        file_count: 1,
        published: {
          id: "skill-2",
          slug: "research",
          discoverable: true,
          cover_image_url: null,
          icon_url: null,
          view_count: 4,
        },
      }),
    ]);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders skill folders as cards linking to the skill browse route", async () => {
    render(<SkillsPage />);

    // The name appears in quick-access and the card grid; every instance
    // must link to the skill browse route.
    const launchLinks = (await screen.findAllByText("Launch Plan")).map((el) =>
      el.closest("a"),
    );
    expect(launchLinks.length).toBeGreaterThan(0);
    for (const link of launchLinks) {
      expect(link).toHaveAttribute("href", "/skills/folder/folder-1");
    }
    expect(screen.getByText("How we launch")).toBeInTheDocument();

    // Unpublished skills badge as Private; published ones say Published.
    expect(screen.getByText("Private")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    const researchLinks = screen
      .getAllByText("Research")
      .map((el) => el.closest("a"));
    for (const link of researchLinks) {
      expect(link).toHaveAttribute("href", "/skills/folder/folder-2");
    }
  });

  it("sells the CLI create command and Discover when there are no skills", async () => {
    vi.mocked(listSkills).mockResolvedValue([]);

    render(<SkillsPage />);

    expect(await screen.findByText("No skills yet.")).toBeInTheDocument();
    expect(screen.getByText('stash skills create "<name>"')).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /browse Discover/ }),
    ).toBeInTheDocument();
  });

  it("creates the skill server-side and navigates to it", async () => {
    vi.stubGlobal("prompt", vi.fn()
      .mockReturnValueOnce("My Skill")
      .mockReturnValueOnce("Use for release planning."));
    vi.mocked(createSkill).mockResolvedValue({ folder_id: "folder-9", name: "My Skill" });

    render(<SkillsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /New Skill/ }));

    await waitFor(() =>
      expect(createSkill).toHaveBeenCalledWith("My Skill", "Use for release planning."),
    );
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith("/skills/folder/folder-9"),
    );
  });
});
