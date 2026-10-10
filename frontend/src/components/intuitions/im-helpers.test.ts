import { describe, expect, it } from "vitest";
import type { RubricQuestion } from "@/lib/intuition-api";
import {
  describeFeature,
  detectItemKeys,
  groupFeatures,
  invalidatedQuestions,
  mistakeIds,
  parseJsonl,
  pYes,
  rubricProblem,
  uniqueSlug,
} from "./im-helpers";

const rubric: RubricQuestion[] = [
  { id: "answers_question", type: "noul", prompt: "Answers?", criteria: { true: "Engages", false: "Ignores" } },
  { id: "tone", type: "choice", prompt: "Tone?", criteria: { warm: "Friendly", cold: "Curt" } },
  { id: "length", type: "score", prompt: "Length?", criteria: ["Too short", "Right", "Too long"] },
];

describe("describeFeature", () => {
  it("maps yes/no, choice, and score features to their question and option", () => {
    expect(describeFeature("answers_question", rubric)).toMatchObject({ questionId: "answers_question", option: null, optionLabel: "yes" });
    expect(describeFeature("tone=warm", rubric)).toMatchObject({ questionId: "tone", option: "warm", optionLabel: "warm · Friendly" });
    expect(describeFeature("length=2", rubric)).toMatchObject({ questionId: "length", option: "2", optionLabel: "2 · Too long" });
  });

  it("keeps unknown features readable", () => {
    expect(describeFeature("gone=x", rubric)).toMatchObject({ question: null, optionLabel: "x" });
  });

  it("groups consecutive features by question", () => {
    const groups = groupFeatures(["answers_question", "tone=warm", "tone=cold", "length=0"], rubric);
    expect(groups.map((g) => [g.questionId, g.features.map((f) => f.index)])).toEqual([
      ["answers_question", [0]],
      ["tone", [1, 2]],
      ["length", [3]],
    ]);
  });
});

describe("detectItemKeys", () => {
  it("returns shared keys when every item is a flat object with the same keys", () => {
    expect(detectItemKeys([{ customer: "a", reply: "b" }, { reply: "d", customer: "c" }])).toEqual(["customer", "reply"]);
  });

  it("returns null for strings, mixed shapes, nested values, or no items", () => {
    expect(detectItemKeys(["text"])).toBeNull();
    expect(detectItemKeys([{ a: "x" }, { b: "y" }])).toBeNull();
    expect(detectItemKeys([{ a: { nested: true } }])).toBeNull();
    expect(detectItemKeys([])).toBeNull();
  });
});

describe("parseJsonl", () => {
  const labels = [{ id: "send", description: "" }, { id: "edit", description: "" }];

  it("parses labeled and unlabeled lines and reports bad ones", () => {
    const text = [
      '{"item": {"customer": "hi", "reply": "hello"}, "label": "send", "split": "eval"}',
      '{"item": "plain"}',
      "not json",
      '{"item": "x", "label": "nope"}',
      "",
    ].join("\n");
    const { examples, errors } = parseJsonl(text, "choice", labels);
    expect(examples).toHaveLength(2);
    expect(examples[0]).toMatchObject({ label: "send", split: "eval", needs_review: false });
    expect(examples[1]).toMatchObject({ label: null, needs_review: true });
    expect(errors).toEqual(["Line 3: not valid JSON", "Line 4: label must be one of send, edit"]);
  });

  it("accepts pairs only for preference models", () => {
    const line = '{"item": "a", "item_b": "b", "label": "a"}';
    expect(parseJsonl(line, "preference", []).examples).toHaveLength(1);
    expect(parseJsonl(line, "choice", labels).errors[0]).toMatch(/pairs only/);
  });
});

describe("rubric edits", () => {
  it("invalidates only changed questions, or all of them when the description changes", () => {
    const edited = rubric.map((q) => (q.id === "tone" ? { ...q, prompt: "Tone now?" } : q));
    const added = [...rubric, { id: "new_q", type: "noul" as const, prompt: "New?", criteria: { true: "", false: "" } }];
    expect(invalidatedQuestions({ description: "d", rubric }, { description: "d", rubric: edited })).toEqual(["tone"]);
    expect(invalidatedQuestions({ description: "d", rubric }, { description: "d", rubric: added })).toEqual(["new_q"]);
    expect(invalidatedQuestions({ description: "d", rubric }, { description: "e", rubric })).toHaveLength(3);
  });

  it("flags invalid rubrics like the backend", () => {
    expect(rubricProblem("preference", [], rubric)).toBeNull();
    expect(rubricProblem("choice", [{ id: "only", description: "" }], rubric)).toMatch(/2–12 labels/);
    expect(rubricProblem("preference", [], [{ ...rubric[1], criteria: { one: "" } }])).toMatch(/2–12 options/);
    expect(rubricProblem("preference", [], [{ ...rubric[0], id: "Bad Id" }])).toMatch(/slug/);
  });

  it("makes unique slugs", () => {
    expect(uniqueSlug("Tone?", ["tone"])).toBe("tone_2");
    expect(uniqueSlug("", [])).toBe("question");
  });
});

describe("metrics helpers", () => {
  it("collects mistakes from train and held-out rows", () => {
    const evaluation = (rows: { example_id: string; label: string; predicted: string }[]) => ({
      n: rows.length, accuracy: null, log_loss: null, ece: null, confusion: null,
      rows: rows.map((r) => ({ ...r, p_true: 0.5 })),
    });
    const ids = mistakeIds({
      train: evaluation([{ example_id: "1", label: "send", predicted: "edit" }, { example_id: "2", label: "send", predicted: "send" }]),
      eval: evaluation([{ example_id: "3", label: "edit", predicted: "rewrite" }]),
      ungraded_examples: 0,
      fit_options: null,
    });
    expect([...ids].sort()).toEqual(["1", "3"]);
  });

  it("reads P(yes) from yes/no answers", () => {
    expect(pYes({ true: 0.8, false: 0.2 })).toBe(0.8);
    expect(pYes({ false: 0.25 })).toBe(0.75);
    expect(pYes(undefined)).toBeNull();
  });
});
