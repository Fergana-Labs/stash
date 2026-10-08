import { expect, it } from "vitest";
import type { RmStep } from "@/lib/types";
import { presentTrace, isContext, readableExcerpt } from "./trace-presentation";
import { buildTraceOutline, groupPath, resolveGroupPath } from "./trace-outline";
import { rowSteps } from "./trace-rows";

function step(index: number, content: string, role: RmStep["role"] = "assistant"): RmStep {
  return { id: `s${index}`, index, content, role, tool_input: null, tool_name: null, tool_call_id: null, metadata: null };
}

it("keeps immutable sources while numbering calls and results as one step, excluding instructions", () => {
  const original = [step(0, "<skills_instructions>Skills</skills_instructions>", "system"), step(1, "# AGENTS.md instructions\n<INSTRUCTIONS>Rules</INSTRUCTIONS>", "user"), step(2, "Fix it", "user"), { ...step(3, ""), tool_name: "exec", tool_call_id: "c" }, { ...step(4, "Done", "tool"), tool_call_id: "c" }, step(5, "Fixed")];
  const snapshot = structuredClone(original);
  const view = presentTrace(original);
  expect(view.context).toHaveLength(2);
  expect(view.mapSteps.map((s) => s.index)).toEqual([0, 1, 2]);
  expect(view.numberById.get("s3")).toBe(2);
  expect(view.numberById.get("s4")).toBe(2);
  expect(view.numberById.has("s1")).toBe(false);
  expect(original).toEqual(snapshot);
  expect(isContext(step(0, "Please edit AGENTS.md", "user"))).toBe(false);
});

it("builds bounded drill-down groups with every row reachable, including paired outputs", () => {
  const source = [step(0, "Fix the parser", "user"), ...Array.from({ length: 100 }, (_, i) => ({ ...step(i + 1, ""), tool_name: "exec", tool_call_id: `c${i}` })), step(101, "Done"), step(102, "Create a landing page", "user"), step(103, "Created")];
  const view = presentTrace(source);
  const tree = buildTraceOutline(view.rows);
  expect(tree).toHaveLength(2);
  const leaves: string[] = [];
  function visit(nodes: typeof tree) { for (const node of nodes) { expect(node.children.length).toBeLessThanOrEqual(6); if (node.children.length) visit(node.children); else leaves.push(...node.rows.flatMap((row) => rowSteps(row).map((s) => s.id))); } }
  visit(tree);
  expect(leaves).toEqual(source.map((s) => s.id));
  const path = groupPath(tree, "s60");
  expect(path.length).toBeGreaterThan(1);
  expect(resolveGroupPath(tree, path).at(-1)!.rows.some((row) => row.key === "s60")).toBe(true);
});

it("respects recorded task identity and keeps acknowledgements with the preceding task", () => {
  const source = [step(0, "Fix it", "user"), step(1, "Done"), step(2, "thanks", "user"), { ...step(3, "Also a different task", "user"), metadata: { label: { task_id: "second", intent: "new_request" } } }];
  expect(buildTraceOutline(presentTrace(source).rows)).toHaveLength(2);
  expect(readableExcerpt('<image path="/a.png">[input_image]</image>\nFix **this**')).toBe("Fix this");
});
