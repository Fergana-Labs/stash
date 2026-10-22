import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { WizardProvider } from "../wizard-ui";
import LabelerCard, { Labeler } from "./LabelerCard";

const api = vi.hoisted(() => ({ imGet: vi.fn(), imExamples: vi.fn(), imEditExample: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);
vi.mock("@/lib/wizard-api", () => ({ wzReport: vi.fn() }));

const detail = { model: { id: "m", output_type: "choice" }, draft: { labels: [{ id: "send", description: "" }, { id: "rewrite", description: "" }] }, active: null };
const example = (id: string, item: unknown) => ({ id, kind: "item", item, item_b: null, label: null, needs_review: true, note: "", split: "train", source: "human" });

beforeEach(() => vi.clearAllMocks());

it("labels with number keys, shows images, and reports back to the wizard", async () => {
  const user = userEvent.setup();
  api.imGet.mockResolvedValue(detail);
  api.imExamples.mockResolvedValue([
    example("e1", { kind: "image", name: "shot.png", content: "A red button", data_url: "data:image/png;base64,AAAA" }),
    example("e2", "please send"),
    { ...example("e3", "done already"), needs_review: false, label: "send" },
  ]);
  api.imEditExample.mockResolvedValue({});
  const send = vi.fn();
  render(<WizardProvider value={{ modelId: "m", send, refresh: vi.fn(), version: 0, busy: false }}><Labeler which="needs_review" /></WizardProvider>);
  expect(await screen.findByRole("img", { name: "shot.png" })).toBeVisible();
  expect(screen.getByText("1 of 2, press 1–2")).toBeVisible();
  await user.keyboard("2");
  await screen.findByText("please send");
  fireEvent.click(screen.getByRole("button", { name: /send/ }));
  await waitFor(() => expect(send).toHaveBeenCalledWith("Labeled 2 examples: 1 rewrite, 1 send.", "event"));
  expect(api.imEditExample).toHaveBeenNthCalledWith(1, "m", "e1", { label: "rewrite", needs_review: false });
});

it("opens labeling in a modal from the chat, by itself when the wizard just asked", async () => {
  api.imGet.mockResolvedValue(detail);
  api.imExamples.mockResolvedValue([example("e2", "please send")]);
  render(<WizardProvider value={{ modelId: "m", send: vi.fn(), refresh: vi.fn(), version: 0, busy: false }}><LabelerCard fresh /></WizardProvider>);
  expect(await screen.findByRole("dialog", { name: "Label examples" })).toBeVisible();
  expect(await screen.findByText("please send")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Not now" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Label 1" })).toBeVisible();
});
