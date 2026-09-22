import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listSkills, setSkillAgentEnabled, type Skill } from "@/lib/api";
import ActiveSkills from "./ActiveSkills";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", () => ({
  listSkills: vi.fn(),
  setSkillAgentEnabled: vi.fn(),
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

describe("ActiveSkills", () => {
  beforeEach(() => {
    vi.mocked(listSkills).mockResolvedValue([enabledSkill, disabledSkill]);
    vi.mocked(setSkillAgentEnabled).mockResolvedValue();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows only the Skills that are switched on", async () => {
    render(<ActiveSkills />);

    expect(await screen.findByRole("link", { name: /Launch Plan/ })).toHaveAttribute(
      "href",
      "/skills/folder/folder-1",
    );
    expect(screen.queryByRole("link", { name: /Research Notes/ })).not.toBeInTheDocument();
  });

  it("enables an off Skill from the Enable more menu", async () => {
    render(<ActiveSkills />);

    fireEvent.click(await screen.findByRole("button", { name: "Enable more" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Research Notes/ }));

    await waitFor(() =>
      expect(setSkillAgentEnabled).toHaveBeenCalledWith(disabledSkill, true),
    );
    expect(listSkills).toHaveBeenCalledTimes(2);
  });

  it("hides Enable more when every Skill is already on", async () => {
    vi.mocked(listSkills).mockResolvedValue([enabledSkill]);
    render(<ActiveSkills />);

    await screen.findByRole("link", { name: /Launch Plan/ });
    expect(screen.queryByRole("button", { name: "Enable more" })).not.toBeInTheDocument();
  });
});
