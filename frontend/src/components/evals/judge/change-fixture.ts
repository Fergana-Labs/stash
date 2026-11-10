import type { EvalProposal } from "@/lib/evals-api";

const tally = (right: number, n: number) => ({ n, right, agreement: n ? right / n : null, good_above_bad: 1 });
export const now = new Date().toISOString();
const example = (id: string, extra = {}) => ({
  id, name: "", asked: "", text: `output ${id}`, files: [], label: "bad" as const, note: "", held_out: false, created_at: now,
  added_by_name: "Reviewer", added_via: "web" as const, caller: "", ...extra,
});
export const proposal = (extra: Partial<EvalProposal> = {}): EvalProposal => ({
  id: "p2", number: 2, base: 4, status: "open", source: "revised", scoring: "mean", instructions: "",
  traits: [
    { name: "Color", good: "warm red", bad: "blue" },
    { name: "Stripes", good: "plain", bad: "striped" },
    { name: "Size", good: "large", bad: "small" },
  ],
  changes: [
    { kind: "add", trait: "Stripes", why: "the striped ones are bad" },
    { kind: "tighten", trait: "Color", why: "orange passed as red" },
  ],
  before: { number: 4, scoring: "mean", instructions: "", traits: [{ name: "Color", good: "red", bad: "blue" }, { name: "Size", good: "large", bad: "small" }, { name: "Shape", good: "round", bad: "square" }] },
  checks: {
    before: { fit: tally(6, 8), check: tally(3, 4) }, after: { fit: tally(8, 8), check: tally(4, 4) },
    fixed: [{ id: "e1", before: 1, after: 0 }], broke: [], evidence: ["e1", "e2"],
    calls: { n: 10, mean_before: 0.71, mean_after: 0.64, pass_before: 8, pass_after: 7, changed: [{ id: "c1", before: 0.8, after: 0.3 }], calls: [{ id: "c1", before: 0.8, after: 0.3 }] },
    manipulation: { n: 3, resisted: 3, worst: { score: 0.1, base: 0, claim: "" } }, short: null,
  },
  passed: true, quality: { before: { score: 82, parts: {} }, after: { score: 97, parts: {} } },
  proposed_by: null, decided_by: null, decided_at: null, note: "", version: null, stale: false,
  examples: { e1: example("e1", { note: "striped" }), e2: example("e2", { caller: "support-agent" }) },
  calls: { c1: { id: "c1", name: "", asked: "draw a chart", text: "", files: [], caller: "support-agent", created_at: now } },
  comments: [],
  created_at: now, ...extra,
});
