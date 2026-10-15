import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { WizardEvent } from "@/lib/wizard-api";
import WizardChat from "./WizardChat";
import { stageWizardMessage } from "./wizard-navigation";

const api = vi.hoisted(() => ({ get: vi.fn(), draft: vi.fn(), stream: vi.fn(), router: { replace: vi.fn() } }));
vi.mock("@/lib/wizard-api", async () => ({
  ...await vi.importActual("@/lib/wizard-api"), wzGet: api.get, wzSaveDraft: api.draft, streamWizard: api.stream,
}));
vi.mock("next/navigation", () => ({ useRouter: () => api.router }));
vi.mock("./ModelPanel", () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  api.draft.mockResolvedValue({ saved: true });
  api.get.mockResolvedValue({ id: "session", model_id: "eval", title: "Slide quality", transcript: [] });
  api.stream.mockImplementation(async (_id: string, _text: string, _kind: string, event: (e: WizardEvent) => void) => {
    event({ type: "text", delta: "Ready to help." });
    event({ type: "done", model_id: "eval" });
  });
});

it("keeps setup focused without exposing an unfinished eval navigation link", async () => {
  render(<WizardChat sessionId="session" />);
  expect(await screen.findByRole("heading", { name: "Slide quality" })).toBeVisible();
  expect(screen.queryByRole("link", { name: "Back to eval →" })).not.toBeInTheDocument();
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


it("keeps a message as draft input when submitting it fails", async () => {
  api.stream.mockRejectedValueOnce(new Error("Connection lost"));
  render(<WizardChat sessionId="session" />);
  await screen.findByRole("heading", { name: "Slide quality" });
  const input = screen.getByRole("textbox", { name: "Message the wizard" });
  fireEvent.change(input, { target: { value: "Do not lose this setup" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Connection lost");
  await waitFor(() => expect(input).toHaveValue("Do not lose this setup"));
});


it("opens a completed eval instead of resuming its setup chat", async () => {
  api.get.mockResolvedValue({ id: "session", model_id: "eval", title: "Slide quality", status: "saved", transcript: [] });
  render(<WizardChat sessionId="session" />);
  await waitFor(() => expect(api.router.replace).toHaveBeenCalledWith("/reward-models/evals/eval"));
  expect(api.stream).not.toHaveBeenCalled();
});

it("finishes setup when the trained version is saved", async () => {
  stageWizardMessage("session", { id: 1, text: "Save this eval.", kind: "message" });
  api.stream.mockImplementation(async (_id: string, _text: string, _kind: string, event: (e: WizardEvent) => void) => {
    event({ type: "complete", model_id: "eval" });
  });
  render(<WizardChat sessionId="session" />);
  await waitFor(() => expect(api.router.replace).toHaveBeenCalledWith("/reward-models/evals/eval"));
});
