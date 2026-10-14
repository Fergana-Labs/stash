import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { WizardProvider } from "@/components/wizard/wizard-ui";
import InboxPanel from "./InboxPanel";

const im = vi.hoisted(() => ({ imGet: vi.fn() }));
const wz = vi.hoisted(() => ({ wzQueue: vi.fn(), wzTriage: vi.fn(), wzResolve: vi.fn(), wzTopics: vi.fn(), wzRefreshTopics: vi.fn() }));
vi.mock("@/lib/intuition-api", () => im);
vi.mock("@/lib/wizard-api", () => wz);

const row = (id: string, item: unknown, label: string) => ({ id, kind: "predict", input: { item }, output: { label }, confidence: 0.58, caller: "api", status: "unreviewed", version: 2, example_id: null, created_at: "2026-10-14T12:00:00Z" });
const wrap = (send = vi.fn()) => render(<WizardProvider value={{ modelId: "m", send, refresh: vi.fn(), version: 0, busy: false }}><InboxPanel /></WizardProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  wz.wzTopics.mockResolvedValue({ computed_at: null, topics: [] });
  wz.wzResolve.mockResolvedValue({ status: "labeled", example: null });
  wz.wzTriage.mockResolvedValue({ status: "dismissed", example: null });
});

it("confirms or corrects with a reason and a pin, one inbox for everything", async () => {
  im.imGet.mockResolvedValue({ model: { id: "m", output_type: "choice" }, active: { labels: [{ id: "send", description: "" }, { id: "rewrite", description: "" }] }, draft: null });
  wz.wzQueue.mockResolvedValue({ items: [row("p1", { question: "Refund after 45 days?", answer: "Sure, anytime!" }, "send"), row("p2", "spam spam", "send")] });
  const send = vi.fn();
  wrap(send);
  // Objects that read as a conversation render as one, not as JSON.
  expect(await screen.findByText("Refund after 45 days?")).toBeVisible();
  expect(screen.getByText("Question")).toBeVisible();
  expect(wz.wzQueue).toHaveBeenCalledWith("m", "all", null);

  fireEvent.click(screen.getByText("Refund after 45 days?"));
  fireEvent.change(screen.getByLabelText("Why"), { target: { value: "Policy is 30 days" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: /rewrite/ }));
  await waitFor(() => expect(wz.wzResolve).toHaveBeenCalledWith("m", "p1", { label: "rewrite", note: "Policy is 30 days", pin: true }));

  fireEvent.click(await screen.findByText("spam spam"));
  fireEvent.click(screen.getByRole("button", { name: "Ignore" }));
  await waitFor(() => expect(wz.wzTriage).toHaveBeenCalledWith("m", "p2", "ignore"));
  fireEvent.click(await screen.findByRole("button", { name: /Done \(2 reviewed\)/ }));
  expect(send).toHaveBeenCalledWith("Reviewed 2 from the inbox: 1 corrected, 1 ignored.", "event");
});

it("labels multi-issue decisions as a set", async () => {
  im.imGet.mockResolvedValue({ model: { id: "m", output_type: "multi" }, active: { labels: [{ id: "background", description: "" }, { id: "watermark", description: "" }] }, draft: null });
  wz.wzQueue.mockResolvedValue({ items: [row("p3", "a photo", "watermark")] });
  wrap();
  fireEvent.click(await screen.findByText("a photo"));
  fireEvent.click(screen.getByRole("button", { name: /background/ }));
  fireEvent.click(screen.getByRole("button", { name: /^Save/ }));
  await waitFor(() => expect(wz.wzResolve).toHaveBeenCalledWith("m", "p3", { label: "background+watermark", note: "", pin: false }));
});
