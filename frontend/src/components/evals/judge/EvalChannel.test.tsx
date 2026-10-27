import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi, type Mock } from "vitest";
import type { EvalAttachment, EvalLabel, EvalMessage } from "@/lib/evals-api";
import EvalChannel, { type Send } from "./EvalChannel";

// eslint-disable-next-line @next/next/no-img-element -- stands in for the authenticated thumbnail
vi.mock("./FileThumb", () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }));

const attachment = (id: string, label: EvalAttachment["label"] = null, extra: Partial<EvalAttachment> = {}): EvalAttachment =>
  ({ example_id: id, name: `${id}.png`, content_type: "image/png", label, note: "", held_out: false, ...extra });
const message = (id: string, extra: Partial<EvalMessage> = {}): EvalMessage => ({
  id, thread_id: null, author: "user", kind: "message", text: "", data: {}, attachments: [], about: null,
  created_at: new Date().toISOString(), ...extra,
});

let onSend: Mock<(send: Send, onProgress: (sent: number) => void) => Promise<void>>;
let onLabel: Mock<(exampleId: string, label: EvalLabel | null) => Promise<void>>;
let onRemove: Mock<(exampleId: string) => Promise<void>>;
beforeEach(() => {
  onRemove = vi.fn<(exampleId: string) => Promise<void>>().mockResolvedValue(undefined);
  onSend = vi.fn<(send: Send, onProgress: (sent: number) => void) => Promise<void>>().mockResolvedValue(undefined);
  onLabel = vi.fn<(exampleId: string, label: EvalLabel | null) => Promise<void>>().mockResolvedValue(undefined);
});
const show = (messages: EvalMessage[]) =>
  render(<EvalChannel evalId="e" messages={messages} onSend={onSend} onLabel={onLabel} onRemove={onRemove} />);

it("folds the agent's reply into a thread, like Slack, and a choice answers in that thread", async () => {
  show([
    message("m1", { attachments: [attachment("a1"), attachment("a2")] }),
    message("m2", { thread_id: "m1", author: "agent", text: "Good or bad?", data: { choices: ["All good", "All bad"] } }),
  ]);
  // Folded: the reply count stands out because the agent is waiting on the person.
  expect(screen.queryByText("Good or bad?")).toBeNull();
  const count = screen.getByText("1 reply");
  expect(count).toHaveClass("font-semibold");
  expect(screen.getByRole("button", { expanded: false })).toHaveTextContent("Agent");
  fireEvent.click(count);
  expect(screen.getByText("Good or bad?")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "All bad" }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith({ text: "All bad", files: [], threadId: "m1" }, expect.any(Function)));
  fireEvent.click(screen.getByRole("button", { name: "Hide replies" }));
  expect(screen.queryByText("Good or bad?")).toBeNull();
});

it("keeps answered threads folded behind their reply count", () => {
  show([
    message("m1", { text: "these are bad" }),
    message("m2", { thread_id: "m1", author: "agent", text: "Which ones?" }),
    message("m3", { thread_id: "m1", text: "all of them" }),
  ]);
  expect(screen.queryByText("all of them")).toBeNull();
  expect(screen.getByText("2 replies")).not.toHaveClass("font-semibold");
  fireEvent.click(screen.getByText("2 replies"));
  expect(screen.getByText("all of them")).toBeVisible();
});

it("labels an attachment from its buttons, and clicking the active label clears it", async () => {
  show([message("m1", { attachments: [attachment("a1", "good", { held_out: true, note: "clean layout" })] })]);
  const group = screen.getByRole("group", { name: "Label a1.png" });
  expect(within(group).getByRole("button", { name: "Good" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Held out")).toBeVisible();
  expect(screen.getByRole("figure")).toHaveAttribute("title", "clean layout");
  fireEvent.click(within(group).getByRole("button", { name: "Bad" }));
  await waitFor(() => expect(onLabel).toHaveBeenCalledWith("a1", "bad"));
  fireEvent.click(within(group).getByRole("button", { name: "Good" }));
  await waitFor(() => expect(onLabel).toHaveBeenCalledWith("a1", null));
});

it("takes a file out of the eval with its X", async () => {
  show([message("m1", { attachments: [attachment("a1", "good"), attachment("a2", "bad")] })]);
  fireEvent.click(screen.getByRole("button", { name: "Remove a2.png" }));
  await waitFor(() => expect(onRemove).toHaveBeenCalledWith("a2"));
  expect(onLabel).not.toHaveBeenCalled();
});

it("shows what a rubric update changed and why, as a reply in the thread", () => {
  show([
    message("m0", { text: "these are bad, striped" }),
    message("m1", {
      thread_id: "m0", author: "agent", kind: "rubric", text: "Rubric v2: added Stripes. Agrees with 8 of 8 examples it learned from (was 6 of 8).",
      data: { version: 2, changes: [{ kind: "add", trait: "Stripes", why: "the striped ones are bad" }] },
    }),
  ]);
  expect(screen.queryByText(/Rubric v2: added Stripes/)).toBeNull();
  // A report isn't waiting on anyone, so its count doesn't stand out.
  expect(screen.getByText("1 reply")).not.toHaveClass("font-semibold");
  fireEvent.click(screen.getByText("1 reply"));
  expect(screen.getByText(/Rubric v2: added Stripes/)).toBeVisible();
  expect(screen.getByText("Added Stripes")).toBeVisible();
  expect(screen.getByText(": the striped ones are bad")).toBeVisible();
});

it("sends on Enter, keeps Shift+Enter for new lines, and sends pasted screenshots", async () => {
  show([message("m1", { text: "hello" })]);
  const box = screen.getByRole("textbox", { name: "Message" });
  fireEvent.change(box, { target: { value: "these are bad" } });
  fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
  expect(onSend).not.toHaveBeenCalled();
  const shot = new File(["png"], "shot.png", { type: "image/png" });
  fireEvent.paste(box, { clipboardData: { files: [shot] } });
  expect(screen.getByRole("button", { name: "Remove shot.png" })).toBeVisible();
  fireEvent.keyDown(box, { key: "Enter" });
  await waitFor(() => expect(onSend).toHaveBeenCalledWith({ text: "these are bad", files: [shot] }, expect.any(Function)));
  await waitFor(() => expect(box).toHaveValue(""));
});

it("starts empty with a drop box, and shows no reading indicator", () => {
  show([]);
  expect(screen.getByText("Drop screenshots of good and bad agent work")).toBeVisible();
  expect(screen.queryByRole("status")).toBeNull();
});
