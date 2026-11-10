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
const show = (messages: EvalMessage[], reading = false) =>
  render(<EvalChannel evalId="e" messages={messages} reading={reading} onSend={onSend} onLabel={onLabel} onRemove={onRemove} />);

it("runs as one conversation: the agent's messages are in line, and a choice answers its question", async () => {
  show([
    message("m1", { attachments: [attachment("a1"), attachment("a2")], created_at: "2026-11-10T10:00:00Z" }),
    message("m2", { thread_id: "m1", author: "agent", text: "Good or bad?", data: { choices: ["All good", "All bad"] }, created_at: "2026-11-10T10:01:00Z" }),
  ]);
  // Nobody is named: the person's message and the agent's are told apart by where they sit.
  expect(screen.queryByText("Agent")).toBeNull();
  expect(screen.queryByText("You")).toBeNull();
  expect(screen.getByRole("article", { name: "Agent message" })).toHaveTextContent("Good or bad?");
  expect(within(screen.getByRole("article", { name: "Your message" })).getAllByRole("figure")).toHaveLength(2);
  // The agent's turn is marked by how long it worked on the person's message.
  expect(within(screen.getByRole("article", { name: "Agent message" })).getByText("Worked for 1m 0s")).toBeVisible();
  // Nothing is folded away, and there are no per-message reply boxes.
  expect(screen.getByText("Good or bad?")).toBeVisible();
  expect(screen.queryByText("1 reply")).toBeNull();
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "All bad" }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith({ text: "All bad", files: [], threadId: "m1" }, expect.any(Function)));
});

it("shows every message in the order it was sent, and what is typed continues the latest exchange", async () => {
  show([
    message("m3", { thread_id: "m1", text: "all of them", created_at: "2026-11-10T10:02:00Z" }),
    message("m1", { text: "these are bad", created_at: "2026-11-10T10:00:00Z" }),
    message("m4", { text: "one more thing", created_at: "2026-11-10T10:03:00Z" }),
    message("m2", { thread_id: "m1", author: "agent", text: "Which ones?", created_at: "2026-11-10T10:01:00Z" }),
    message("m5", { thread_id: "m4", author: "agent", text: "Go on", created_at: "2026-11-10T10:04:00Z" }),
  ]);
  expect(screen.getAllByRole("article").map((a) => a.querySelector("p")?.textContent)).toEqual(["these are bad", "Which ones?", "all of them", "one more thing", "Go on"]);
  expect(screen.getAllByText(/^Worked for /).map((w) => w.textContent)).toEqual(["Worked for 1m 0s", "Worked for 1m 0s"]);
  const box = screen.getByRole("textbox", { name: "Message" });
  fireEvent.change(box, { target: { value: "never use gradients" } });
  fireEvent.keyDown(box, { key: "Enter" });
  await waitFor(() => expect(onSend).toHaveBeenCalledWith({ text: "never use gradients", files: [], threadId: "m4" }, expect.any(Function)));
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

it("shows what a rubric update changed and why, in line", () => {
  show([
    message("m0", { text: "these are bad, striped", created_at: "2026-11-10T10:00:00Z" }),
    message("m1", {
      thread_id: "m0", author: "agent", kind: "rubric", text: "Rubric v2: added Stripes. Agrees with 8 of 8 examples it learned from (was 6 of 8).",
      data: { version: 2, changes: [{ kind: "add", trait: "Stripes", why: "the striped ones are bad" }] }, created_at: "2026-11-10T10:01:00Z",
    }),
  ]);
  expect(screen.getByText(/Rubric v2: added Stripes/)).toBeVisible();
  expect(screen.getByText("Added Stripes")).toBeVisible();
  expect(screen.getByText(": the striped ones are bad")).toBeVisible();
});

it("sends on Enter, keeps Shift+Enter for new lines, and sends pasted screenshots", async () => {
  show([]);
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

it("shows the agent typing at the end of the conversation while it reads an unread message", () => {
  const talk = [
    message("m1", { text: "hello?", created_at: "2026-11-10T10:00:00Z" }),
    message("m2", { thread_id: "m1", author: "agent", text: "Hey", created_at: "2026-11-10T10:01:00Z" }),
    message("m3", { thread_id: "m1", text: "these are bad", unread: true, created_at: "2026-11-10T10:02:00Z" }),
  ];
  const { rerender } = show(talk, true);
  expect(screen.getAllByRole("status", { name: "Agent is replying" })).toHaveLength(1);
  rerender(<EvalChannel evalId="e" messages={talk} reading={false} onSend={onSend} onLabel={onLabel} onRemove={onRemove} />);
  expect(screen.queryByRole("status", { name: "Agent is replying" })).toBeNull();
  rerender(<EvalChannel evalId="e" messages={talk.map((m) => ({ ...m, unread: false }))} reading onSend={onSend} onLabel={onLabel} onRemove={onRemove} />);
  expect(screen.queryByRole("status", { name: "Agent is replying" })).toBeNull();
});
