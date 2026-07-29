// Running a skill from the launcher. The load-bearing part is what reaches the
// agent, and what does not: a skill only reaches the launcher once it is in
// your Skills, so a run must never install anything.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SkillLauncher from "./SkillLauncher";
import { takeSkillRun } from "@/lib/skill-launch";
import { useWorkspace, type WorkspaceState } from "@/lib/workspace-store";

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const openTab = vi.fn();

vi.mock("@/lib/workspace-store", () => ({
  useWorkspace: vi.fn(),
}));

const skill = {
  name: "resurface",
  description: "Old saves worth revisiting.",
  when_to_use: "When the user asks what they have forgotten.",
};

beforeEach(() => {
  // The launcher reads exactly one slice of the store, so a stub with just
  // that member is enough to drive it.
  vi.mocked(useWorkspace).mockImplementation((selector) =>
    selector({ openTab } as unknown as WorkspaceState),
  );
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
  it("shows the skill's own frontmatter and nothing authored for the launcher", () => {
    render(<SkillLauncher skill={skill} onClose={vi.fn()} />);

    expect(screen.getByText("Old saves worth revisiting.")).toBeInTheDocument();
    expect(
      screen.getByText("When the user asks what they have forgotten."),
    ).toBeInTheDocument();
  });

  it("will not run an empty request", () => {
    render(<SkillLauncher skill={skill} onClose={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
  });

  it("names the skill so the run is not left to the agent's routing", async () => {
    render(<SkillLauncher skill={skill} onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "What should I revisit?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await waitFor(() => expect(openTab).toHaveBeenCalled());
    expect(takeSkillRun(openedTabRef())).toBe(
      "Use the resurface skill.\n\nWhat should I revisit?",
    );
    expect(router.push).toHaveBeenCalledWith("/agents");
  });

  it("opens its own chat per run", async () => {
    render(<SkillLauncher skill={skill} onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Go" } });
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await waitFor(() => expect(openTab).toHaveBeenCalled());
    const [kind, refId, title] = openTab.mock.calls[0];
    expect(kind).toBe("agent");
    expect(refId).toMatch(/^new-run-/);
    expect(title).toBe("Run: resurface");
  });
});
