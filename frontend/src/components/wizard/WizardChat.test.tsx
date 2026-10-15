import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { WizardEvent } from "@/lib/wizard-api";
import WizardChat from "./WizardChat";
import { stageWizardMessage } from "./wizard-navigation";

const api = vi.hoisted(() => ({ get: vi.fn(), stream: vi.fn() }));
vi.mock("@/lib/wizard-api", async () => ({
  ...await vi.importActual("@/lib/wizard-api"), wzGet: api.get, streamWizard: api.stream,
}));
vi.mock("./ModelPanel", () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  api.get.mockResolvedValue({ id: "session", model_id: "eval", title: "Slide quality", transcript: [] });
  api.stream.mockImplementation(async (_id: string, _text: string, _kind: string, event: (e: WizardEvent) => void) => {
    event({ type: "text", delta: "Ready to help." });
    event({ type: "done", model_id: "eval" });
  });
});

it("opens the full-page conversation and provides a way back to its eval", async () => {
  render(<WizardChat sessionId="session" />);
  expect(await screen.findByRole("heading", { name: "Slide quality" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Back to eval →" })).toHaveAttribute("href", "/reward-models/evals/eval");
  expect(api.stream).not.toHaveBeenCalled();
});

it("carries a workspace request into the wizard once, without replaying it on return", async () => {
  stageWizardMessage("session", { id: 1, text: "Help me set up this eval.", kind: "message" });
  const view = render(<WizardChat sessionId="session" />);
  await screen.findByText("Ready to help.");
  await waitFor(() => expect(api.stream).toHaveBeenCalledTimes(1));
  expect(api.stream).toHaveBeenCalledWith("session", "Help me set up this eval.", "message", expect.any(Function));
  view.unmount();
  render(<WizardChat sessionId="session" />);
  await screen.findByRole("heading", { name: "Slide quality" });
  expect(api.stream).toHaveBeenCalledTimes(1);
});
