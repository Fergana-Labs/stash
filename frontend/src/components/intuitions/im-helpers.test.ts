import { describe, expect, it } from "vitest";
import type { Example, Head, RubricQuestion } from "@/lib/intuition-api";
import {
  answerSummary,
  byLabelAnswers,
  describeFeature,
  detectItemKeys,
  driverBar,
  driverScale,
  examplesToJsonl,
  fieldProvenance,
  groupFeatures,
  invalidatedQuestions,
  isFlagged,
  mistakeIds,
  parseBatchInput,
  parseJsonl,
  pYes,
  questionImportance,
  questionVerdict,
  separatingOption,
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

describe("flags and provenance", () => {
  it("knows which labels are flagged", () => {
    const labels = [{ id: "send", description: "" }, { id: "rewrite", description: "", flag: true }];
    expect(isFlagged(labels, "rewrite")).toBe(true);
    expect(isFlagged(labels, "send")).toBe(false);
    expect(isFlagged(undefined, "send")).toBe(false);
  });

  it("tags agent_* and environment_* fields", () => {
    expect(fieldProvenance("agent_final_message")).toBe("agent");
    expect(fieldProvenance("environment_final_page")).toBe("environment");
    expect(fieldProvenance("user_goal")).toBeNull();
  });
});

describe("drivers", () => {
  const drivers = [
    { question_id: "a", prompt: "A?", contribution: 0.8 },
    { question_id: "b", prompt: "B?", contribution: -0.4 },
    { question_id: "c", prompt: "C?", contribution: 0 },
  ];

  it("scales bars to the largest contribution, half the track each side", () => {
    const scale = driverScale(drivers);
    expect(scale).toBe(0.8);
    expect(driverBar(0.8, scale)).toEqual({ side: "pos", width: 50 });
    expect(driverBar(-0.4, scale)).toEqual({ side: "neg", width: 25 });
    expect(driverBar(Number.NaN, scale)).toEqual({ side: "pos", width: 0 });
  });

  it("never divides by zero", () => {
    const scale = driverScale([{ question_id: "z", prompt: "", contribution: 0 }]);
    expect(scale).toBeGreaterThan(0);
    expect(driverBar(0, scale).width).toBe(0);
    expect(driverScale([])).toBeGreaterThan(0);
  });

  it("summarizes rubric answers compactly", () => {
    expect(answerSummary(rubric[0], { true: 0.72, false: 0.28 })).toBe("yes 72%");
    expect(answerSummary(rubric[0], { true: 0.1, false: 0.9 })).toBe("no 90%");
    expect(answerSummary(rubric[1], { warm: 0.3, cold: 0.7 })).toBe("cold 70%");
    expect(answerSummary(rubric[2], { "0": 0.1, "1": 0.8, "2": 0.1 })).toBe("1 · Right 80%");
    expect(answerSummary(rubric[0], undefined)).toBeNull();
  });
});

describe("question diagnostics", () => {
  it("measures importance as the weight spread across classes, per question", () => {
    const head = {
      feature_names: ["answers_question", "tone=warm", "tone=cold"],
      classes: ["send", "edit"],
      weights: [
        [1, 0.5, -0.5],
        [-1, 0, 0],
      ],
    } as unknown as Head;
    const importance = questionImportance(head, rubric);
    expect(importance.get("answers_question")).toBe(2);
    expect(importance.get("tone")).toBe(1);
    const scoreHead = { feature_names: ["answers_question"], classes: ["score"], weights: [[-0.7]] } as unknown as Head;
    expect(questionImportance(scoreHead, rubric).get("answers_question")).toBeCloseTo(0.7);
    expect(questionImportance(null, rubric).size).toBe(0);
  });

  it("reads the ablation", () => {
    const ab = (accuracy_drop: number | null, log_loss_rise: number | null) => ({ accuracy_without: null, log_loss_without: null, accuracy_drop, log_loss_rise });
    expect(questionVerdict(ab(0.05, 0.1))).toBe("helps");
    expect(questionVerdict(ab(0, 0.1))).toBe("calibration");
    expect(questionVerdict(ab(0, -0.03))).toBe("none");
    expect(questionVerdict(ab(-0.05, 0.02))).toBe("hurts");
    expect(questionVerdict(null)).toBeNull();
    expect(questionVerdict(ab(null, null))).toBeNull();
  });

  it("picks the option that best separates the labels", () => {
    const rows = byLabelAnswers(rubric[1], "tone", { send: { "tone=warm": 0.5, "tone=cold": 0.5 }, edit: { "tone=warm": 0.45, "tone=cold": 0.05 } });
    expect(separatingOption(rows)).toBe("cold");
    expect(separatingOption([])).toBeUndefined();
  });

  it("lays out mean answers by label in label order", () => {
    const yesNo = byLabelAnswers(rubric[0], "answers_question", { edit: { answers_question: 0.3 }, send: { answers_question: 0.9 } }, ["send", "edit"]);
    expect(yesNo).toEqual([
      { label: "send", values: [{ key: "answers_question", text: "P(yes)", value: 0.9 }] },
      { label: "edit", values: [{ key: "answers_question", text: "P(yes)", value: 0.3 }] },
    ]);
    const choice = byLabelAnswers(rubric[1], "tone", { send: { "tone=warm": 0.8, "tone=cold": 0.2 } });
    expect(choice[0].values.map((v) => [v.key, v.value])).toEqual([
      ["warm", 0.8],
      ["cold", 0.2],
    ]);
  });
});

describe("parseBatchInput", () => {
  const allowed = ["send", "edit"];

  it("accepts wrapped items, JSON strings, bare objects and plain text", () => {
    const text = ['{"item": {"customer": "hi", "reply": "yo"}, "label": "send"}', '"a json string"', '{"customer": "x", "reply": "y"}', "plain text line", ""].join("\n");
    const { items, labels, errors } = parseBatchInput(text, allowed);
    expect(errors).toEqual([]);
    expect(items).toEqual([{ customer: "hi", reply: "yo" }, "a json string", { customer: "x", reply: "y" }, "plain text line"]);
    expect(labels).toEqual(["send", null, null, null]);
  });

  it("reports bad JSON, unknown labels, empty items and non-string labels by line", () => {
    const text = ['{"item": "x", "label": "nope"}', '{"item": "x"', '{"item": ""}', '{"item": "x", "label": 3}', "[1, 2]"].join("\n");
    expect(parseBatchInput(text, allowed).errors).toEqual([
      "Line 1: label must be one of send, edit",
      "Line 2: not valid JSON",
      "Line 3: item is empty",
      'Line 4: "label" must be a string',
      "Line 5: item must be text or a JSON object",
    ]);
  });

  it("caps the number of items", () => {
    const text = Array.from({ length: 4 }, (_, i) => `item ${i}`).join("\n");
    expect(parseBatchInput(text, null, 3).errors[0]).toBe("4 items; at most 3 per run");
    expect(parseBatchInput(text, null, 4).errors).toEqual([]);
  });

  it("round-trips examples exported as eval lines", () => {
    const examples = [
      { item: { customer: "a", reply: "b" }, item_b: null, label: "send" },
      { item: "unlabeled", item_b: null, label: null },
      { item: "pair a", item_b: "pair b", label: "a" },
    ] as Example[];
    const parsed = parseBatchInput(examplesToJsonl(examples), allowed);
    expect(parsed.errors).toEqual([]);
    expect(parsed.items).toEqual([{ customer: "a", reply: "b" }, "unlabeled"]);
    expect(parsed.labels).toEqual(["send", null]);
  });
});
