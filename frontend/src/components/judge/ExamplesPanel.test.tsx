import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { WizardProvider } from "@/components/wizard/wizard-ui";
import ExamplesPanel from "./ExamplesPanel";

const api = vi.hoisted(() => ({ imGet: vi.fn(), imExamples: vi.fn(), imEditExample: vi.fn() }));
vi.mock("@/lib/intuition-api", async (original) => ({ ...await original<typeof import("@/lib/intuition-api")>(), ...api }));
vi.mock("@/components/wizard/cards/GoldenCard", () => ({ default: () => null }));
vi.mock("@/components/wizard/cards/LabelerCard", () => ({ LabelerModal: () => null }));
const sample = { id: "e1", item: { customer: "Can I return this?", reply: "Return within 30 days." }, item_b: null, kind: "item", label: "send", needs_review: false, source: "human", split: "eval", pinned: true, note: "Policy is correct" };
function wrap(onTry = vi.fn()) { return render(<WizardProvider value={{ modelId: "m", send: vi.fn(), refresh: vi.fn(), version: 0, busy: false }}><ExamplesPanel onTry={onTry} /></WizardProvider>); }
beforeEach(() => {
  vi.clearAllMocks();
  api.imGet.mockResolvedValue({ model: { output_type: "choice" }, active: { labels: [{ id: "send" }, { id: "rewrite" }] } });
  api.imExamples.mockResolvedValue([sample]); api.imEditExample.mockResolvedValue({});
});

it("shows a compact table and opens the original structured input in the sandbox", async () => {
  const onTry = vi.fn(); wrap(onTry);
  const table = await screen.findByRole("table", { name: "Golden set examples" });
  expect(within(table).getByText("Held out")).toBeVisible();
  expect(within(table).getByText("pinned")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Open in sandbox" }));
  expect(onTry).toHaveBeenCalledWith(sample.item);
  fireEvent.click(screen.getByRole("button", { name: "Inspect example 1" }));
  expect(screen.getByRole("region", { name: "Example 1" })).toHaveTextContent("Can I return this?");
  const feedback = screen.getByRole("textbox", { name: "Why this label?" });
  fireEvent.change(feedback, { target: { value: "Matches the return policy" } });
  fireEvent.blur(feedback);
  await waitFor(() => expect(api.imEditExample).toHaveBeenCalledWith("m", "e1", { note: "Matches the return policy" }));
});

it("preserves multi-issue labels and exposes both inputs of a preference pair", async () => {
  api.imGet.mockResolvedValue({ model: { output_type: "multi" }, draft: { labels: [{ id: "tone" }, { id: "accuracy" }] } });
  api.imExamples.mockResolvedValue([{ ...sample, label: "accuracy+tone" }]);
  const view = wrap();
  fireEvent.click(await screen.findByRole("button", { name: "Inspect example 1" }));
  expect(screen.getByRole("button", { name: /accuracy/ })).toHaveAttribute("aria-pressed", "true");
  view.unmount();
  api.imExamples.mockResolvedValue([{ ...sample, kind: "pair", item_b: { reply: "Contact support for an exception." }, label: "a" }]);
  const onTry = vi.fn(); wrap(onTry);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect example 1" }));
  fireEvent.click(screen.getByRole("button", { name: "Open B in sandbox" }));
  expect(onTry).toHaveBeenCalledWith({ reply: "Contact support for an exception." });
});
