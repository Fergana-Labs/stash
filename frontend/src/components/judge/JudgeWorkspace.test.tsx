import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ get: vi.fn(), sessions: vi.fn(), create: vi.fn(), router: { push: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => api.router }));
vi.mock("@/lib/intuition-api", async (original) => ({ ...await original<typeof import("@/lib/intuition-api")>(), imGet: api.get }));
vi.mock("@/lib/wizard-api", async (original) => ({ ...await original<typeof import("@/lib/wizard-api")>(), wzReport: async () => ({ report: null }), wzSessions: api.sessions, wzCreate: api.create }));
vi.mock("@/components/wizard/cards/BriefCard", () => ({ default: () => null }));
vi.mock("@/components/wizard/cards/CriteriaCard", () => ({ default: () => null }));
vi.mock("@/components/wizard/cards/PlaygroundCard", () => ({ default: () => null }));
vi.mock("./UseIt", async (original) => ({ ...await original<typeof import("./UseIt")>(), default: () => null }));
vi.mock("@/components/evals/RefinePanel", () => ({ default: () => null }));
vi.mock("./ResultsPanel", async () => {
  const { useWizard } = await import("@/components/wizard/wizard-ui");
  return { default: function Results() { const { send } = useWizard(); return <button onClick={() => send("Change the refund criterion")}>Change criteria</button>; } };
});
import JudgeWorkspace from "./JudgeWorkspace";

it("hands ongoing edits to the user's MCP agent without reopening the wizard", async () => {
  api.get.mockResolvedValue({ model: { id: "eval", name: "Support replies", brief: {} }, counts: { labeled: 8 }, active: { number: 1, description: "Review replies", provider: "jev", metrics: null }, draft: null, judge: { providers: {} } });
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<JudgeWorkspace id="eval" />);
  await screen.findByRole("button", { name: "Edit via MCP" });
  expect(screen.queryByRole("button", { name: "Wizard" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Resume setup" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Results" }));
  fireEvent.click(screen.getByRole("button", { name: "Change criteria" }));
  await screen.findByRole("dialog");
  fireEvent.click(screen.getByRole("button", { name: "Copy edit instructions" }));
  await waitFor(() => expect(writeText).toHaveBeenCalled());
  expect(writeText.mock.calls[0][0]).toContain('intuition_id="eval"');
  expect(writeText.mock.calls[0][0]).toContain('Change the refund criterion');
  expect(writeText.mock.calls[0][0]).toContain('set_criteria');
  expect(api.sessions).not.toHaveBeenCalled();
  expect(api.create).not.toHaveBeenCalled();
  expect(api.router.push).not.toHaveBeenCalled();
});
