// Running a skill from the launcher. The load-bearing part is what reaches the
// agent: a skill that was never installed leaves the agent improvising, and a
// prompt that never gets staged opens an empty chat.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SkillLauncher from "./SkillLauncher";
import { installSkill } from "@/lib/api";
import { takeSkillRun } from "@/lib/skill-launch";
import { useWorkspace, type WorkspaceState } from "@/lib/workspace-store";

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

vi.mock("@/lib/api", () => ({ installSkill: vi.fn() }));

const openTab = vi.fn();

vi.mock("@/lib/workspace-store", () => ({
  useWorkspace: vi.fn(),
}));

const publicSkill = {
  name: "resurface",
  slug: "resurface-abc123",
  description: "Old saves worth revisiting.",
  when_to_use: "When the user asks what they have forgotten.",
  examples: ["What should I revisit this week?", "Find old saves about agents."],
};

beforeEach(() => {
  // The launcher reads exactly one slice of the store, so a stub with just
  // that member is enough to drive it.
  vi.mocked(useWorkspace).mockImplementation((selector) =>
    selector({ openTab } as unknown as WorkspaceState),
  );
  vi.mocked(installSkill).mockResolvedValue({
    folder_id: "folder-1",
    name: "resurface",
    installed: true,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** The refId the launcher opened its chat tab with. */
function openedTabRef(): string {
  return openTab.mock.calls[0][1];
}

describe("SkillLauncher", () => {
  it("seeds the request with the skill's first starter prompt", () => {
    render(<SkillLauncher skill={publicSkill} onClose={vi.fn()} />);

    expect(screen.getByRole("textbox")).toHaveValue("What should I revisit this week?");
  });

  it("swaps the request when another starter prompt is picked", () => {
    render(<SkillLauncher skill={publicSkill} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Find old saves about agents." }));

    expect(screen.getByRole("textbox")).toHaveValue("Find old saves about agents.");
  });

  it("installs a published skill before running it, and sends the skill by name", async () => {
    render(<SkillLauncher skill={publicSkill} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await waitFor(() => expect(openTab).toHaveBeenCalled());
    expect(installSkill).toHaveBeenCalledWith("resurface-abc123");
    expect(takeSkillRun(openedTabRef())).toBe(
      "Use the resurface skill.\n\nWhat should I revisit this week?",
    );
    expect(router.push).toHaveBeenCalledWith("/agents");
  });

  it("does not install a skill you already hold", async () => {
    const held = { ...publicSkill, slug: null };
    render(<SkillLauncher skill={held} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await waitFor(() => expect(openTab).toHaveBeenCalled());
    expect(installSkill).not.toHaveBeenCalled();
  });

  it("runs the edited request, not the starter prompt it began as", async () => {
    render(<SkillLauncher skill={publicSkill} onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Only the agent stuff." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await waitFor(() => expect(openTab).toHaveBeenCalled());
    expect(takeSkillRun(openedTabRef())).toBe(
      "Use the resurface skill.\n\nOnly the agent stuff.",
    );
  });

  it("keeps the dialog open and says why when the install fails", async () => {
    vi.mocked(installSkill).mockRejectedValue(new Error("Skill not found"));
    render(<SkillLauncher skill={publicSkill} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    expect(await screen.findByText("Skill not found")).toBeInTheDocument();
    expect(openTab).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });
});
