import { describe, expect, it } from "vitest";
import type { RmAnnotation, RmStep } from "@/lib/types";
import { buildSegments, diffLines, locateQuote, quoteFromOffsets, skillFirstLine, sortAnnotations } from "./rm-text";

describe("quote anchoring", () => {
  // The same phrase appears twice; the annotator highlighted the second one.
  // The prefix must steer the highlight back to that occurrence, otherwise a
  // "−" on the bad sentence would render on the good one.
  const content = "Refund issued. Checking policy first. Refund issued to your card.";

  it("round-trips a selection to the occurrence the user selected", () => {
    const start = content.lastIndexOf("Refund issued");
    const quote = quoteFromOffsets(content, start, start + "Refund issued".length);
    expect(quote.prefix.endsWith("policy first. ")).toBe(true);
    expect(locateQuote(content, quote)).toEqual({ start, end: start + "Refund issued".length });
  });

  it("caps context at 32 characters each side", () => {
    const long = "a".repeat(100) + "X" + "b".repeat(100);
    const quote = quoteFromOffsets(long, 100, 101);
    expect(quote.prefix).toHaveLength(32);
    expect(quote.suffix).toHaveLength(32);
  });

  it("returns null instead of guessing when the anchored text is gone", () => {
    expect(locateQuote("totally different", { text: "Refund", prefix: "", suffix: " issued" })).toBeNull();
  });
});

describe("buildSegments", () => {
  it("splits overlapping highlights into flat spans covered by both ids", () => {
    const segments = buildSegments("abcdef", [
      { id: "x", start: 1, end: 4 },
      { id: "y", start: 3, end: 5 },
    ]);
    expect(segments).toEqual([
      { text: "a", ids: [] },
      { text: "bc", ids: ["x"] },
      { text: "d", ids: ["x", "y"] },
      { text: "e", ids: ["y"] },
      { text: "f", ids: [] },
    ]);
  });
});

describe("sortAnnotations", () => {
  const steps: RmStep[] = [0, 1].map((index) => ({
    id: `s${index}`,
    index,
    role: "assistant",
    content: "first part, second part",
    tool_name: null,
    tool_input: null,
    tool_call_id: null,
    metadata: null,
  }));

  function annotation(id: string, step_id: string | null, quoteText: string | null, created_at: string): RmAnnotation {
    return {
      id,
      trace_id: "t",
      step_id,
      rating: null,
      comment: "c",
      quote: quoteText === null ? null : quoteFromOffsets(steps[0].content, steps[0].content.indexOf(quoteText), steps[0].content.indexOf(quoteText) + quoteText.length),
      label_error: false,
      label_error_note: null,
      author_id: "u",
      author_name: "u",
      created_at,
    };
  }

  it("orders the sidebar like the document: trace, then steps, then position in step", () => {
    const sorted = sortAnnotations(
      [
        annotation("step1", "s1", null, "2026-01-01"),
        annotation("second-part", "s0", "second", "2026-01-01"),
        annotation("first-part", "s0", "first", "2026-01-02"),
        annotation("trace", null, null, "2026-01-03"),
      ],
      steps,
    );
    expect(sorted.map((a) => a.id)).toEqual(["trace", "first-part", "second-part", "step1"]);
  });
});

describe("diffLines", () => {
  it("marks removed and added lines between seed and best skill", () => {
    expect(diffLines("keep\nold\nend", "keep\nnew\nend")).toEqual([
      { kind: "same", text: "keep" },
      { kind: "del", text: "old" },
      { kind: "add", text: "new" },
      { kind: "same", text: "end" },
    ]);
  });
});

describe("skillFirstLine", () => {
  // Every candidate shares the same frontmatter, so the list would be useless
  // if it showed "---" or the name line instead of the body.
  it("skips the frontmatter and blank lines to the first body line", () => {
    const skill = "---\nname: refund-requests\ndescription: Handling refunds\n---\n\nCheck the refund policy first.\nThen reply.";
    expect(skillFirstLine(skill)).toBe("Check the refund policy first.");
  });
});
