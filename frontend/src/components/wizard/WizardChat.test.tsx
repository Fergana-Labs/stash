import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { WizardEvent } from "@/lib/wizard-api";
import WizardChat from "./WizardChat";
import { stageWizardMessage } from "./wizard-navigation";

const api = vi.hoisted(() => ({ get: vi.fn(), create: vi.fn(), draft: vi.fn(), stream: vi.fn(), router: { replace: vi.fn() } }));
vi.mock("@/lib/wizard-api", async () => ({
  ...await vi.importActual("@/lib/wizard-api"), wzGet: api.get, wzCreate: api.create, wzSaveDraft: api.draft, streamWizard: api.stream,
}));
vi.mock("next/navigation", () => ({ useRouter: () => api.router }));
vi.mock("./ModelPanel", () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  api.draft.mockResolvedValue({ saved: true });
  api.create.mockResolvedValue({ id: "fresh-session" });
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

it("restarts with the same eval after saving the previous chat's unsent draft", async () => {
  let saved!: (value: { saved: boolean }) => void;
  api.draft.mockImplementation(() => new Promise((resolve) => { saved = resolve; }));
  render(<WizardChat sessionId="session" />);
  await screen.findByRole("heading", { name: "Slide quality" });
  fireEvent.change(screen.getByRole("textbox", { name: "Message the wizard" }), { target: { value: "Keep this thought" } });
  fireEvent.click(screen.getByRole("button", { name: "Restart" }));
  expect(api.draft).toHaveBeenCalledWith("session", "Keep this thought");
  expect(api.create).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Restarting…" })).toBeDisabled();
  saved({ saved: true });
  await waitFor(() => expect(api.router.replace).toHaveBeenCalledWith("/reward-models/wizard/fresh-session"));
  expect(api.create).toHaveBeenCalledExactlyOnceWith("eval");
  expect(api.stream).not.toHaveBeenCalled();
});

it("keeps the current chat and draft available if restarting fails", async () => {
  api.get.mockResolvedValue({ id: "session", model_id: null, title: "New eval", transcript: [{ role: "user", kind: "message", text: "My previous setup" }] });
  api.create.mockRejectedValueOnce(new Error("Could not restart"));
  render(<WizardChat sessionId="session" />);
  await screen.findByText("My previous setup");
  fireEvent.change(screen.getByRole("textbox", { name: "Message the wizard" }), { target: { value: "Unsent draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Restart" }));
  await screen.findByRole("alert");
  expect(screen.getByText("My previous setup")).toBeVisible();
  expect(screen.getByRole("textbox", { name: "Message the wizard" })).toHaveValue("Unsent draft");
  expect(api.router.replace).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Restart" }));
  await waitFor(() => expect(api.router.replace).toHaveBeenCalledWith("/reward-models/wizard/fresh-session"));
  expect(api.create).toHaveBeenLastCalledWith(null);
});

it("waits for an in-flight wizard response before allowing restart", async () => {
  api.stream.mockImplementation(() => new Promise(() => {}));
  stageWizardMessage("session", { id: 1, text: "Use my history", kind: "message" });
  render(<WizardChat sessionId="session" />);
  await screen.findByText("Thinking…");
  expect(screen.getByRole("button", { name: "Restart" })).toBeDisabled();
  expect(api.create).not.toHaveBeenCalled();
});
