// Running a skill from the launcher. The load-bearing part is what reaches the
// agent, and what does not: a skill only reaches the launcher once it is in
// your Skills, so a run must never install anything.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SkillLauncher from "./SkillLauncher";
import { takeSkillRun } from "@/lib/skill-launch";

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const skill = {
  name: "resurface",
  description: "Old saves worth revisiting.",
  when_to_use: "When the user asks what they have forgotten.",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

/** The chat ref the launcher navigated to (/agents?chat=<ref>). */
function launchedRef(): string {
  const url = router.push.mock.calls[0][0] as string;
  return new URLSearchParams(url.split("?")[1]).get("chat")!;
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

    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(takeSkillRun(launchedRef())).toBe(
      "Use the resurface skill.\n\nWhat should I revisit?",
    );
  });

  it("opens its own chat per run on the chat page", async () => {
    render(<SkillLauncher skill={skill} onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Go" } });
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(router.push.mock.calls[0][0]).toMatch(/^\/agents\?chat=new-run-/);
  });
});
