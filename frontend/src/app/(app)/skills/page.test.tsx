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
import {
  addSource,
  createSkill,
  listSkills,
  setSourceBindsSkills,
  syncSource,
  type FolderBackedSkill,
  type Skill,
} from "@/lib/api";
import { ConfirmDialogProvider } from "@/components/ConfirmDialog";

function render(ui: ReactNode) {
  return renderBase(ui, { wrapper: ConfirmDialogProvider });
}

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
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
  addSource: vi.fn(),
  createSkill: vi.fn(),
  deleteFolder: vi.fn(),
  forkSkill: vi.fn(),
  listSkills: vi.fn(),
  setSourceBindsSkills: vi.fn(),
  syncSource: vi.fn(),
  // Real behaviour, not a stub: the page keys pins, selection, and React
  // children off this, so a mock returning undefined collapses the render.
  skillKey: (s: Skill) => (s.backing === "folder" ? s.folder_id : s.source_ref),
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

function skill(overrides: Partial<FolderBackedSkill> = {}): Skill {
  return {
    backing: "folder",
    source_ref: null,
    source_name: null,
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

function sourceSkill(overrides: Partial<Skill> = {}): Skill {
  return {
    backing: "source",
    folder_id: null,
    source_ref: "drive-file-1",
    source_name: "skillz",
    name: "Turbochargers",
    description: "Use when a customer reports boost loss.",
    when_to_use: "",
    version: "",
    mcp_exposed: false,
    file_count: 1,
    updated_at: "2026-08-11T00:00:00Z",
    published: null,
    ...overrides,
  } as Skill;
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

  it("creates the skill through the inline composer and navigates to it", async () => {
    vi.mocked(createSkill).mockResolvedValue({ folder_id: "folder-9", name: "My Skill" });

    render(<SkillsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /New Skill/ }));

    // Both fields are required: a skill can never be created without the
    // agent-trigger description. Submitting incomplete shows why instead of
    // silently ignoring the click (a disabled button reads as broken).
    const create = await screen.findByRole("button", { name: "Create skill" });
    fireEvent.click(create);
    expect(createSkill).not.toHaveBeenCalled();
    expect(screen.getByText("Give the skill a name.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My Skill" } });
    fireEvent.click(create);
    expect(createSkill).not.toHaveBeenCalled();
    expect(
      screen.getByText("Describe when an agent should use it — this is required."),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("When should an agent use it?"), {
      target: { value: "Use for release planning." },
    });
    fireEvent.click(create);

    await waitFor(() =>
      expect(createSkill).toHaveBeenCalledWith("My Skill", "Use for release planning."),
    );
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith("/skills/folder/folder-9"),
    );
  });

  it("connects a pasted Drive folder link and reports when its skills arrive", async () => {
    // The box is labeled "add external skill by link", and a Drive folder is
    // the one truly external kind of skill — pasting its link must work, not
    // bounce the user to the integrations page with an error. And because
    // sync + extraction land seconds later, a single refetch loses the race:
    // the form must keep watching until the folder's skills actually appear,
    // or the user sees a page that claims nothing happened.
    vi.mocked(addSource).mockResolvedValue({ id: "src-1", display_name: "skillz" });

    render(<SkillsPage />);

    fireEvent.change(await screen.findByLabelText("Add external skill by link"), {
      target: { value: "https://drive.google.com/drive/u/0/folders/1bHglufVmdfzMPhX9W6HRfSkJkox8dOBE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Skill" }));

    await waitFor(() =>
      expect(addSource).toHaveBeenCalledWith({
        source_type: "google_drive_folder",
        external_ref: "1bHglufVmdfzMPhX9W6HRfSkJkox8dOBE",
      }),
    );
    await waitFor(() => expect(setSourceBindsSkills).toHaveBeenCalledWith("src-1", true));
    await waitFor(() => expect(syncSource).toHaveBeenCalledWith("src-1"));
    expect(
      await screen.findByText('Connected "skillz" — reading its files now…'),
    ).toBeInTheDocument();

    // The next poll finds the folder's first extracted skill.
    vi.mocked(listSkills).mockResolvedValue([sourceSkill()]);
    expect(
      await screen.findByText('"skillz" is connected: 1 skill added.', undefined, {
        timeout: 4000,
      }),
    ).toBeInTheDocument();
  });

  it("keeps source-backed skills distinct from each other in every list", async () => {
    // They all have folder_id null, so anything still keying off it collapses
    // them onto one React key — which silently drops rows rather than throwing.
    // This is why the page keys off skillKey and not the folder.
    const warn = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(listSkills).mockResolvedValue([
      sourceSkill({ source_ref: "drive-file-1", name: "Turbochargers" }),
      sourceSkill({ source_ref: "drive-file-2", name: "Brake Shoes" }),
    ]);

    render(<SkillsPage />);
    await screen.findAllByText("Turbochargers");

    expect(screen.getAllByText("Brake Shoes").length).toBeGreaterThan(0);
    const duplicateKeyWarnings = warn.mock.calls
      .map((args) => String(args[0]))
      .filter((message) => message.includes("same key"));
    expect(duplicateKeyWarnings).toEqual([]);
    warn.mockRestore();
  });

  it("opens a source-backed skill on its own read-only page", async () => {
    // Read-only is about editing, not about visibility: you must always be
    // able to open a skill and read exactly what an agent will be handed.
    // It goes to the document view, not a folder page it hasn't got.
    vi.mocked(listSkills).mockResolvedValue([sourceSkill({ source_ref: "drive-file-1" })]);

    render(<SkillsPage />);

    const links = (await screen.findAllByText("Turbochargers")).map((el) => el.closest("a"));
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/skills/source/drive-file-1");
    }
    // The badge names the shelf, not the provider: two shelves can hold
    // skills with the same name and the card is where you tell them apart.
    expect(screen.getAllByText("skillz").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Use when a customer reports boost loss."),
    ).toBeInTheDocument();
  });
});
