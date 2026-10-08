import { describe, expect, it } from "vitest";
import type { RmStep } from "@/lib/types";
import { rubricSummary, scoreParts, scoreTone, signed, stepReward } from "./step-rewards";

function step(reward: Record<string, unknown> | null): RmStep {
  return { id: "s1", index: 0, role: "assistant", content: "", tool_name: null, tool_input: null, tool_call_id: null, metadata: reward === null ? null : { reward } };
}

const lookup = {
  base: -0.13,
  base_parts: [{ text: "Lookup", value: -0.03 }, { text: "It returned an error", value: -0.1 }],
  jev: { rubric: "tool", grader: "Jev", question: "How was it used?", short: "its failure led to a change of approach", text: "The call fails…", value: 0.008, probability: 0.58, mode: "adjust" },
  score: -0.122,
  shared: [{ from: "a6", verdict: "rejected", value: -0.038 }],
  shared_total: -0.038,
  total: -0.16,
  is_answer: false,
};

describe("stepReward", () => {
  it("reads a reward from step metadata and ignores anything incomplete", () => {
    expect(stepReward(step(lookup))?.total).toBe(-0.16);
    expect(stepReward(step(null))).toBeNull();
    expect(stepReward(step({ base: -0.03 }))).toBeNull();
  });
});

describe("scoreParts", () => {
  const numberOf = (chunk: string) => (chunk === "a6" ? 12 : null);

  it("lists the rubric lookup, the grade, and each share of a later answer", () => {
    const parts = scoreParts(stepReward(step(lookup))!, numberOf);
    expect(parts.map((p) => [p.text, p.value])).toEqual([
      ["Lookup", -0.03],
      ["It returned an error", -0.1],
      ["Quality check: its failure led to a change of approach", 0.008],
      ["Blame from the answer in step 12 that the user rejected", -0.038],
    ]);
    expect(parts[3].targetChunk).toBe("a6");
  });

  it("strikes the rubric's flat points when the grade replaces them", () => {
    const question = {
      ...lookup,
      base: -0.05,
      base_parts: [{ text: "Question to the user", value: -0.05 }],
      jev: { ...lookup.jev, short: "the reply was used", value: -0.02, mode: "replace" },
      shared: [],
    };
    const [flat, graded] = scoreParts(stepReward(step(question))!, numberOf);
    expect(flat).toEqual(expect.objectContaining({ text: "Question to the user", replaced: -0.05 }));
    expect(flat.value).toBeUndefined();
    expect(graded).toEqual(expect.objectContaining({ text: "Quality check: the reply was used", value: -0.02 }));
  });

  it("names a share without a step number when the answer is not in the trace", () => {
    const [share] = scoreParts(stepReward(step({ ...lookup, base_parts: [], jev: null, shared: [{ from: "a99", verdict: "confirmed", value: 0.2 }] }))!, numberOf);
    expect(share).toEqual(expect.objectContaining({ text: "Credit from the answer that the user confirmed", tone: "good" }));
  });
});

describe("formatting", () => {
  it("rounds to two signed decimals", () => {
    expect(signed(0.3)).toBe("+0.30");
    expect(signed(-0.0441)).toBe("−0.04");
    expect(signed(-0.004)).toBe("0.00");
  });

  it("colours by size: free, small cost, real penalty, gain", () => {
    expect(scoreTone(0)).toBe("neutral");
    expect(scoreTone(-0.03)).toBe("warn");
    expect(scoreTone(-0.2)).toBe("bad");
    expect(scoreTone(0.3)).toBe("good");
  });
});

describe("rubricSummary", () => {
  it("parses a trace's task scores and signals", () => {
    const summary = rubricSummary({
      score: -0.64,
      episodes: [{ task: "t1", score: -0.64, rubric_b_only: -0.71, answer: -0.16, costs: -0.48, has_answer: true }],
      signals: { rejections: 2, confirmations: 0, tool_errors: 3, answers: 3 },
    });
    expect(summary?.episodes[0]).toEqual({ task: "t1", score: -0.64, rubricOnly: -0.71, answer: -0.16, costs: -0.48, hasAnswer: true });
    expect(summary?.signals.rejections).toBe(2);
    expect(rubricSummary(undefined)).toBeNull();
    expect(rubricSummary({ score: 1 })).toBeNull();
  });
});
