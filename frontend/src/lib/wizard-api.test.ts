import { expect, it } from "vitest";
import { applyEvent, type AssistantPart } from "./wizard-api";

it("builds an assistant turn from streamed events in order", () => {
  let parts: AssistantPart[] = [];
  parts = applyEvent(parts, { type: "text", delta: "Let me " });
  parts = applyEvent(parts, { type: "text", delta: "train it." });
  parts = applyEvent(parts, { type: "activity", id: "t1", tool: "train", label: "Training", status: "running" });
  parts = applyEvent(parts, { type: "progress", id: "t1", stage: "grading", message: "Asked Jev about 4 of 9 items", done: 4, total: 9 });
  expect(parts[1]).toMatchObject({ type: "activity", progress: "Asked Jev about 4 of 9 items" });
  parts = applyEvent(parts, { type: "activity", id: "t1", tool: "train", label: "Training", status: "done" });
  parts = applyEvent(parts, { type: "card", id: "c1", kind: "report", props: {} });
  parts = applyEvent(parts, { type: "text", delta: "Done." });
  expect(parts.map((p) => p.type)).toEqual(["text", "activity", "card", "text"]);
  expect(parts[0]).toEqual({ type: "text", text: "Let me train it." });
  expect(parts[1]).toMatchObject({ status: "done", progress: undefined });
});
