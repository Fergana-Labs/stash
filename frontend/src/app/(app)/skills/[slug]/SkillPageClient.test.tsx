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
import SkillPageClient from "./SkillPageClient";
import {
  ShellChromeProvider,
  useShellChromeValue,
} from "../../../../components/ShellChromeContext";
import { ConfirmDialogProvider } from "../../../../components/ConfirmDialog";
import {
  getPublicSkill,
  listObjectShares,
  shareObjectByEmail,
  unpublishSkill,
  updateSkill,
  type PublicSkillDetail,
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
  forkSkill: vi.fn(),
  getPublicSkill: vi.fn(),
  githubOwner: (url: string) =>
    url.replace("https://github.com/", "").split("/")[0],
  listObjectShares: vi.fn(),
  publishSkillFolder: vi.fn(),
  shareObjectByEmail: vi.fn(),
  unpublishSkill: vi.fn(),
  unshareObject: vi.fn(),
  updateSkill: vi.fn(),
  uploadFile: vi.fn(),
  getToken: vi.fn(() => "test-token"),
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
    <ConfirmDialogProvider>
      <ShellChromeProvider>
        <SharedHeader />
        <main>{children}</main>
      </ShellChromeProvider>
    </ConfirmDialogProvider>
  );
}

function SharedHeader() {
  const { shareAction } = useShellChromeValue();
  return <header>{shareAction}</header>;
}

function renderSkill(ui: ReactNode) {
  return render(ui, { wrapper: ShellChromeHarness });
}

function emptyContents(): PublicSkillDetail["contents"] {
  return { subfolders: [], pages: [], files: [], tables: [] };
}

function skillDetail(
  skill: Partial<PublicSkillDetail["skill"]> = {},
): PublicSkillDetail {
  return {
    skill: {
      id: "skill-1",
      workspace_id: "workspace-1",
      folder_id: "folder-1",
      slug: "shared-skill",
      title: "Shared Skill",
      description: "",
      owner_id: "user-1",
      owner_name: "henry",
      owner_display_name: "Henry",
      discoverable: false,
      cover_image_url: null,
      icon_url: null,
      source_github_url: null,
      view_count: 0,
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
      ...skill,
    },
    workspace_name: "Demo Workspace",
    folder_name: "Shared Skill",
    contents: emptyContents(),
    can_write: false,
  };
}

describe("SkillPageClient", () => {
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
    window.history.pushState({}, "", "/skills/shared-skill");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(getPublicSkill).mockResolvedValue({
      ...skillDetail(),
      can_write: true,
    });
    vi.mocked(listObjectShares).mockResolvedValue([]);
    vi.mocked(updateSkill).mockImplementation(async (_skillId, updates) => ({
      ...skillDetail().skill,
      ...updates,
    }));
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the publish popover in the app header with a copy-link affordance", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    const publishButton = await screen.findByRole("button", { name: "Published" });
    expect(
      screen.getByRole("button", { name: "Copy agent handoff link" }),
    ).toBeInTheDocument();
    expect(publishButton.closest("header")).not.toBeNull();

    fireEvent.click(publishButton);
    // Popover renders a "Copy" button for the public URL; click it.
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/skills/shared-skill`,
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument(),
    );
  });

  it("copies an agent-readable handoff link from the app header", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    const handoffButton = await screen.findByRole("button", {
      name: "Copy agent handoff link",
    });
    fireEvent.click(handoffButton);

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/api/v1/skills/shared-skill?format=text`,
      ),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Copy agent handoff link" }),
      ).toHaveTextContent("Copied"),
    );
  });

  it("toggles the Discover listing from the publish popover", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    fireEvent.click(await screen.findByRole("button", { name: "Published" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish skill" });
    fireEvent.click(within(dialog).getByLabelText("List on Discover"));

    await waitFor(() =>
      expect(updateSkill).toHaveBeenCalledWith("skill-1", { discoverable: true }),
    );
  });

  it("unpublishes from the publish popover", async () => {
    vi.mocked(unpublishSkill).mockResolvedValue(undefined);

    renderSkill(<SkillPageClient slug="shared-skill" />);

    fireEvent.click(await screen.findByRole("button", { name: "Published" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish skill" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Unpublish" }));
    const confirmDialog = await screen.findByRole("alertdialog", {
      name: "Unpublish this skill?",
    });
    fireEvent.click(within(confirmDialog).getByRole("button", { name: "Unpublish" }));

    await waitFor(() => expect(unpublishSkill).toHaveBeenCalledWith("skill-1"));
  });

  it("shares the skill folder person-to-person via the generic share button", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Share Shared Skill",
    });
    expect(listObjectShares).toHaveBeenCalledWith("folder", "folder-1");

    fireEvent.change(within(dialog).getByPlaceholderText("Add people by email"), {
      target: { value: "sam@example.com" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Invite" }));

    await waitFor(() =>
      expect(shareObjectByEmail).toHaveBeenCalledWith(
        "folder",
        "folder-1",
        "sam@example.com",
        "read",
      ),
    );
  });

  it("shows the settings link for writers and the fork CTA for readers", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    expect(
      await screen.findByRole("link", { name: "Skill settings" }),
    ).toHaveAttribute("href", "/skills/shared-skill/settings");
    expect(
      screen.queryByRole("button", { name: "Add to my files" }),
    ).not.toBeInTheDocument();

    cleanup();
    vi.mocked(getPublicSkill).mockResolvedValueOnce(skillDetail());
    renderSkill(<SkillPageClient slug="shared-skill" />);

    expect(
      await screen.findByRole("button", { name: "Add to my files" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Skill settings" }),
    ).not.toBeInTheDocument();
  });

  it("shows the skill author in the detail header", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce(
      skillDetail({ owner_name: "sam", owner_display_name: "Sam" })
    );

    renderSkill(<SkillPageClient slug="shared-skill" />);

    expect(await screen.findByText("by Sam")).toBeInTheDocument();
  });

  it("links the GitHub source in the header only for imported skills", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce(
      skillDetail({ source_github_url: "https://github.com/acme/skills/tree/main/cooking" })
    );

    renderSkill(<SkillPageClient slug="shared-skill" />);

    const link = await screen.findByRole("link", { name: /GitHub/ });
    expect(link.getAttribute("href")).toBe(
      "https://github.com/acme/skills/tree/main/cooking"
    );
    // Credit goes to the repo owner, not the curator account that imported it.
    expect(screen.getByText("by acme")).toBeInTheDocument();

    cleanup();
    vi.mocked(getPublicSkill).mockResolvedValueOnce(skillDetail());
    renderSkill(<SkillPageClient slug="shared-skill" />);
    await screen.findByText("by Henry");
    expect(screen.queryByRole("link", { name: /GitHub/ })).toBeNull();
  });

  it("renders the SKILL.md intro and rows for the rest of the contents", async () => {
    const detail = skillDetail();
    detail.contents = {
      subfolders: [
        { id: "sub-1", name: "research", parent_folder_id: "folder-1", path: ["research"] },
      ],
      pages: [
        {
          id: "page-md",
          name: "SKILL.md",
          content_type: "markdown",
          content_markdown: "---\nname: Shared Skill\ndescription: \n---\n\n# How to launch\n",
          content_html: "",
          html_layout: "responsive",
          updated_at: "2026-05-11T00:00:00Z",
          folder_path: [],
        },
        {
          id: "page-2",
          name: "Plan",
          content_type: "markdown",
          content_markdown: "# Plan",
          content_html: "",
          html_layout: "responsive",
          updated_at: "2026-05-11T00:00:00Z",
          folder_path: ["research"],
        },
      ],
      files: [
        {
          id: "file-1",
          name: "shot.png",
          content_type: "image/png",
          size_bytes: 1234,
          url: "https://files.test/shot.png",
          created_at: "2026-05-11T00:00:00Z",
          linked_table_id: null,
          folder_path: [],
        },
      ],
      tables: [
        {
          id: "table-1",
          name: "Budget",
          description: "",
          columns: [],
          rows: [],
          folder_path: [],
        },
      ],
    };
    vi.mocked(getPublicSkill).mockResolvedValueOnce(detail);

    renderSkill(<SkillPageClient slug="shared-skill" />);

    // SKILL.md body renders as the intro, with frontmatter stripped.
    expect(
      await screen.findByRole("heading", { name: "How to launch" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/name: Shared Skill/)).not.toBeInTheDocument();
    // SKILL.md itself doesn't get its own row.
    expect(screen.queryByText("SKILL.md")).not.toBeInTheDocument();

    expect(screen.getByRole("link", { name: /Plan/ })).toHaveAttribute(
      "href",
      "/p/page-2?skill=shared-skill",
    );
    expect(screen.getByRole("link", { name: /shot\.png/ })).toHaveAttribute(
      "href",
      "/f/file-1?skill=shared-skill",
    );
    expect(screen.getByRole("link", { name: /Budget/ })).toHaveAttribute(
      "href",
      "/tables/table-1?skill=shared-skill",
    );
    // Subfolder items group under their folder path.
    expect(screen.getByRole("heading", { name: "research" })).toBeInTheDocument();
  });
});
