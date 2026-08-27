import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listSkills, setSkillAgentEnabled, type Skill } from "@/lib/api";
import SkillsPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/api", () => ({
  listSkills: vi.fn(),
  setSkillAgentEnabled: vi.fn(),
  createSkill: vi.fn(),
  getToken: vi.fn(() => null),
  getMe: vi.fn(),
  clearToken: vi.fn(),
  revokeStoredApiKey: vi.fn(),
}));

vi.mock("@/lib/skillNavigationCache", () => ({
  refreshSidebar: vi.fn(() => Promise.resolve()),
}));

const enabledSkill: Skill = {
  backing: "folder",
  folder_id: "folder-1",
  source_ref: null,
  source_id: null,
  source_name: null,
  name: "Launch Plan",
  description: "How we launch",
  when_to_use: "",
  version: "",
  mcp_exposed: false,
  file_count: 3,
  updated_at: "2026-06-01T00:00:00Z",
  has_instructions: true,
  published: null,
  agent_enabled: true,
};

const disabledSkill: Skill = {
  ...enabledSkill,
  folder_id: "folder-2",
  name: "Research Notes",
  description: "How we investigate",
  agent_enabled: false,
};

describe("SkillsPage", () => {
  beforeEach(() => {
    vi.mocked(listSkills).mockResolvedValue([enabledSkill, disabledSkill]);
    vi.mocked(setSkillAgentEnabled).mockResolvedValue();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("lists Skills with their real agent-enabled state", async () => {
    render(<SkillsPage />);

    expect(
      await screen.findByRole("link", { name: /Launch Plan/ }),
    ).toHaveAttribute("href", "/skills/folder/folder-1");
    expect(
      screen.getByRole("link", { name: /Research Notes/ }),
    ).toHaveAttribute("href", "/skills/folder/folder-2");
    expect(screen.getByRole("switch", { name: "Enabled" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("switch", { name: "Not enabled" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.queryByText("Grid")).not.toBeInTheDocument();
    expect(screen.queryByText("Recent")).not.toBeInTheDocument();
  });

  it("changes whether a Skill is provided to agents", async () => {
    render(<SkillsPage />);
    fireEvent.click(await screen.findByRole("switch", { name: "Enabled" }));
    await waitFor(() =>
      expect(setSkillAgentEnabled).toHaveBeenCalledWith(enabledSkill, false),
    );
  });

  it("keeps manual Skill creation behind Advanced", async () => {
    vi.mocked(listSkills).mockResolvedValue([]);
    render(<SkillsPage />);
    expect(await screen.findByText(/No Skills yet/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "New Skill" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Advanced" }));
    fireEvent.click(screen.getByRole("button", { name: "New Skill" }));
    expect(
      screen.getByRole("button", { name: /Create skill/i }),
    ).toBeInTheDocument();
  });
});
