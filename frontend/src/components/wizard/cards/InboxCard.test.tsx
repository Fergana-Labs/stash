import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { WizardProvider } from "../wizard-ui";
import InboxCard from "./InboxCard";

const im = vi.hoisted(() => ({ imGet: vi.fn() }));
const wz = vi.hoisted(() => ({ wzQueue: vi.fn(), wzTriage: vi.fn(), wzResolve: vi.fn() }));
vi.mock("@/lib/intuition-api", () => im);
vi.mock("@/lib/wizard-api", () => wz);

const detail = { model: { id: "m", output_type: "choice" }, active: { labels: [{ id: "send", description: "" }, { id: "rewrite", description: "" }] }, draft: null };
const row = (id: string, text: string, extra = {}) => ({ id, kind: "predict", input: { item: text }, output: { label: "send" }, confidence: 0.61, caller: "api", status: "unreviewed", version: 2, example_id: null, created_at: "", ...extra });
const wrap = (ui: React.ReactNode, send = vi.fn()) => render(<WizardProvider value={{ modelId: "m", send, refresh: vi.fn(), version: 0, busy: false }}>{ui}</WizardProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  im.imGet.mockResolvedValue(detail);
  wz.wzTriage.mockResolvedValue({ status: "labeled", example: null });
  wz.wzResolve.mockResolvedValue({ status: "labeled", example: null });
});

it("triages with Y/N/X and reports the tally", async () => {
  wz.wzQueue.mockResolvedValue({ items: [row("p1", "first reply"), row("p2", "second reply")] });
  const send = vi.fn();
  wrap(<InboxCard />, send);
  await screen.findByText("first reply");
  expect(screen.getByText(/The judge said/)).toHaveTextContent("send (61% sure)");
  fireEvent.keyDown(window, { key: "y" });
  await screen.findByText("second reply");
  fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "not sure about tone" } });
  fireEvent.click(screen.getByRole("button", { name: /Needs review/ }));
  await screen.findByText("All caught up.");
  expect(wz.wzTriage).toHaveBeenNthCalledWith(1, "m", "p1", "looks_right", "");
  expect(wz.wzTriage).toHaveBeenNthCalledWith(2, "m", "p2", "escalate", "not sure about tone");
  fireEvent.click(screen.getByRole("button", { name: "Done" }));
  expect(send).toHaveBeenCalledWith("Reviewed 2 in the triage queue: 1 looks right, 1 escalate.", "event");
});

it("expert review records the right answer, the reason, and a pin", async () => {
  wz.wzQueue.mockResolvedValue({ items: [row("p9", "please, but wrong", { status: "escalated", escalation_note: "tone ok, facts wrong" })] });
  wrap(<InboxCard queue="expert" />);
  expect(await screen.findByText("tone ok, facts wrong")).toBeVisible();
  const save = screen.getByRole("button", { name: "Add to golden set" });
  expect(save).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "rewrite" }));
  fireEvent.change(screen.getByLabelText("Why"), { target: { value: "Quotes the wrong refund policy" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(save);
  await waitFor(() => expect(wz.wzResolve).toHaveBeenCalledWith("m", "p9", { label: "rewrite", note: "Quotes the wrong refund policy", pin: true }));
  expect(wz.wzQueue).toHaveBeenCalledWith("m", "expert", null);
});
