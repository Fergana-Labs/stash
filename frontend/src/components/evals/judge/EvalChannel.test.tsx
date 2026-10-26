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
beforeEach(() => {
  onSend = vi.fn<(send: Send, onProgress: (sent: number) => void) => Promise<void>>().mockResolvedValue(undefined);
  onLabel = vi.fn<(exampleId: string, label: EvalLabel | null) => Promise<void>>().mockResolvedValue(undefined);
});
const show = (messages: EvalMessage[], busy = false) =>
  render(<EvalChannel evalId="e" messages={messages} busy={busy} onSend={onSend} onLabel={onLabel} />);

it("opens a thread the agent is waiting on, and a choice answers in that thread", async () => {
  show([
    message("m1", { attachments: [attachment("a1"), attachment("a2")] }),
    message("m2", { thread_id: "m1", author: "agent", text: "Good or bad?", data: { choices: ["All good", "All bad"] } }),
  ]);
  expect(screen.getByText("Good or bad?")).toBeVisible();
  expect(screen.getByRole("button", { name: "Hide replies" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "All bad" }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith({ text: "All bad", files: [], threadId: "m1" }, expect.any(Function)));
});

it("hides a waiting thread when asked, and opens it again when the agent says more", () => {
  const asked = [
    message("m1", { attachments: [attachment("a1")] }),
    message("m2", { thread_id: "m1", author: "agent", text: "Good or bad?" }),
  ];
  const view = show(asked);
  fireEvent.click(screen.getByRole("button", { name: "Hide replies" }));
  expect(screen.queryByText("Good or bad?")).toBeNull();
  view.rerender(<EvalChannel evalId="e" messages={[...asked, message("m3", { thread_id: "m1", author: "agent", text: "Still there?" })]} busy={false} onSend={onSend} onLabel={onLabel} />);
  expect(screen.getByText("Still there?")).toBeVisible();
});

it("keeps answered threads folded behind their reply count", () => {
  show([
    message("m1", { text: "these are bad" }),
    message("m2", { thread_id: "m1", author: "agent", text: "Which ones?" }),
    message("m3", { thread_id: "m1", text: "all of them" }),
  ]);
  expect(screen.queryByText("all of them")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "2 replies" }));
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

it("shows what a rubric update changed and why", () => {
  show([message("m1", {
    author: "agent", kind: "rubric", text: "Rubric v2: added Stripes. Agrees with 8 of 8 examples it learned from (was 6 of 8).",
    data: { version: 2, changes: [{ kind: "add", trait: "Stripes", why: "the striped ones are bad" }] },
  })]);
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

it("starts empty with a drop box, and shows when the agent is reading", () => {
  show([], true);
  expect(screen.getByText("Drop screenshots of good and bad agent work")).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("Reading");
});
