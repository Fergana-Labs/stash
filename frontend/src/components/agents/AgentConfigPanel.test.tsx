import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  listAgents: vi.fn().mockResolvedValue([
    {
      id: "ag1",
      name: "Test agent",
      model_provider: null,
      system_prompt: null,
      run_mode: "chat",
      schedule_cron: null,
      schedule_prompt: null,
      slack_bound: false,
      telegram_bound: false,
      is_default: false,
      is_curator: false,
    },
  ]),
  getAgentPrompt: vi.fn().mockResolvedValue(null),
  updateAgent: vi.fn(),
  deleteAgent: vi.fn(),
  recomputeMemory: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

vi.mock("@/lib/agentChat", () => ({ streamAgentRun: vi.fn() }));
vi.mock("@/lib/agent-tab-view", () => ({ takeCuratorRun: vi.fn(() => null) }));

import AgentConfigPanel from "./AgentConfigPanel";

describe("AgentConfigPanel model dropdown", () => {
  it("offers the local model (pi) option", async () => {
    const user = userEvent.setup();
    render(<AgentConfigPanel agentId="ag1" />);

    // Panel loads the agent, then exposes the Model select.
    const trigger = await screen.findByRole("combobox");
    await user.click(trigger);

    const options = await screen.findAllByRole("option");
    const labels = options.map((o) => o.textContent);
    expect(labels).toContain("Local model (pi)");
    expect(labels).toContain("Auto (your connected model)");
    expect(labels).toContain("Claude Code");
    expect(labels).toContain("Codex");
    expect(labels).toContain("OpenRouter (GLM 5.2 managed)");
  });
});
