import { expect, it, vi } from "vitest";

vi.mock("@/lib/intuition-api", () => ({}));
const { parsePasted } = await import("./UploaderCard");

it("reads JSONL, CSV with a label column, --- blocks and plain lines", () => {
  expect(parsePasted('{"text": "hi", "label": "send"}\n{"text": "bye", "label": "nope"}', ["send", "rewrite"])).toEqual([
    { item: "hi", label: "send", needs_review: false },
    { item: "bye", label: null, needs_review: true },
  ]);
  expect(parsePasted("text,label\nthanks so much,send\nno,rewrite", ["send", "rewrite"]).map((e) => [e.item, e.label])).toEqual([["thanks so much", "send"], ["no", "rewrite"]]);
  expect(parsePasted("first\nstill first\n---\nsecond", [])).toHaveLength(2);
  expect(parsePasted("a\nb\n\nc", [])).toHaveLength(3);
});
