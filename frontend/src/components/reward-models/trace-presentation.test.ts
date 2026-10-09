import { expect, it } from "vitest";
import type { RmStep } from "@/lib/types";
import { presentTrace, readableExcerpt } from "./trace-presentation";
import { buildTraceOutline, groupPath, isContextGroup, resolveGroupPath } from "./trace-outline";
import { rowSteps } from "./trace-rows";

function step(index: number, content: string, role: RmStep["role"] = "assistant"): RmStep {
  return { id: `s${index}`, index, content, role, tool_input: null, tool_name: null, tool_call_id: null, metadata: null };
}

it("keeps immutable sources while numbering calls and results as one step without extracting any roles", () => {
  const original = [step(0, "<skills_instructions>Skills</skills_instructions>", "system"), step(1, "# AGENTS.md instructions\n<INSTRUCTIONS>Rules</INSTRUCTIONS>", "user"), step(2, "Fix it", "user"), { ...step(3, ""), tool_name: "exec", tool_call_id: "c" }, { ...step(4, "Done", "tool"), tool_call_id: "c" }, step(5, "Fixed")];
  const snapshot = structuredClone(original);
  const view = presentTrace(original);
  expect(view.rows.flatMap(rowSteps).map((step) => step.id)).toEqual(original.map((step) => step.id));
  expect(view.mapSteps.map((s) => s.index)).toEqual([0, 1, 2, 3, 4]);
  expect(view.numberById.get("s3")).toBe(4);
  expect(view.numberById.get("s4")).toBe(4);
  expect(view.numberById.get("s1")).toBe(2);
  expect(original).toEqual(snapshot);
});

it("keeps a continuous run of work intact with every row reachable", () => {
  const source = [step(0, "Fix the parser", "user"), ...Array.from({ length: 100 }, (_, i) => ({ ...step(i + 1, ""), tool_name: "exec", tool_call_id: `c${i}` })), step(101, "Done"), step(102, "Create a landing page", "user"), step(103, "Created")];
  const view = presentTrace(source);
  const tree = buildTraceOutline(view.rows);
  expect(tree).toHaveLength(2);
  const leaves: string[] = [];
  function visit(nodes: typeof tree) { for (const node of nodes) { if (node.children.length) visit(node.children); else leaves.push(...node.rows.flatMap((row) => rowSteps(row).map((s) => s.id))); } }
  visit(tree);
  expect(leaves).toEqual(source.map((s) => s.id));
  const path = groupPath(tree, "s60");
  expect(path).toHaveLength(1);
  expect(resolveGroupPath(tree, path).at(-1)!.rows.some((row) => row.key === "s60")).toBe(true);
});

it("respects recorded task identity and keeps acknowledgements with the preceding task", () => {
  const source = [step(0, "Fix it", "user"), step(1, "Done"), step(2, "thanks", "user"), { ...step(3, "Also a different task", "user"), metadata: { label: { task_id: "second", intent: "new_request" } } }];
  expect(buildTraceOutline(presentTrace(source).rows)).toHaveLength(2);
  expect(readableExcerpt('<image path="/a.png">[input_image]</image>\nFix **this**')).toBe("Fix this");
});


it("keeps all tasks separate regardless of their number or length", () => {
  const source = Array.from({ length: 53 }, (_, task) => [step(task * 21, `Request ${task}`, "user"), ...Array.from({ length: 20 }, (_, i) => step(task * 21 + i + 1, `Action ${i}`))]).flat();
  const tree = buildTraceOutline(presentTrace(source).rows);
  const leaves: string[] = [];
  function visit(nodes: typeof tree) {
    for (const node of nodes) {
      if (node.children.length) visit(node.children);
      else { leaves.push(...node.rows.map((row) => row.key)); }
    }
  }
  visit(tree);
  expect(tree).toHaveLength(53);
  expect(tree.every((node) => node.rows.length === 21 && node.children.length === 0)).toBe(true);
  expect(leaves).toEqual(source.map((s) => s.id));
  for (const id of ["s0", "s600", "s1112"]) expect(resolveGroupPath(tree, groupPath(tree, id)).at(-1)?.rows.some((row) => row.key === id)).toBe(true);
});


it("keeps unrelated requests separate even when the next one starts with Also", () => {
  const source = [step(0, "Buy me a burrito", "user"), step(1, "Order confirmed"), step(2, "Also build me a web app", "user"), step(3, "Created the project")];
  const tree = buildTraceOutline(presentTrace(source).rows);
  expect(tree).toHaveLength(2);
  expect(tree.map((node) => node.rows.map((row) => row.key))).toEqual([["s0", "s1"], ["s2", "s3"]]);
});


it("nests distinct activities under recorded progress subtasks without capping either level", () => {
  let index = 0;
  const source: RmStep[] = [step(index++, "Build the web app", "user")];
  for (let phase = 0; phase < 6; phase++) {
    source.push({ ...step(index++, `Implement feature ${phase}`), metadata: { phase: "commentary" } });
    source.push({ ...step(index++, ""), tool_name: "read_file", tool_input: { path: `feature${phase}.ts` } });
    source.push({ ...step(index++, ""), tool_name: "apply_patch", tool_input: { patch: "Fix feature" } });
    source.push({ ...step(index++, ""), tool_name: "exec_command", tool_input: { cmd: "npm test" } });
  }
  const tree = buildTraceOutline(presentTrace(source).rows);
  expect(tree).toHaveLength(1);
  expect(tree[0].children).toHaveLength(6);
  expect(tree[0].children.every((node) => node.children.length === 3)).toBe(true);
  expect(groupPath(tree, "s10")).toHaveLength(3);
  const leaves = tree.flatMap((task) => task.children.flatMap((subtask) => subtask.children.flatMap((node) => node.rows.flatMap(rowSteps))));
  expect(leaves.map((s) => s.id)).toEqual(source.map((s) => s.id));
});


it("keeps startup messages and runtime events in order without manufacturing setup tasks", () => {
  const source = [step(0, "Initial system message", "system"), step(1, "# AGENTS.md instructions", "user"), step(2, "Buy a burrito", "user"), step(3, "Ordering"), step(4, "<turn_aborted>Interrupted</turn_aborted>", "system"), step(5, "Try again", "user"), step(6, "Ordered"), step(7, "Build an app", "user"), step(8, "Done")];
  const tree = buildTraceOutline(presentTrace(source).rows);
  expect(tree.map((node) => node.rows.map((row) => row.key))).toEqual([["s0", "s1", "s2", "s3", "s4"], ["s5", "s6"], ["s7", "s8"]]);
  expect(tree.flatMap((node) => node.rows.flatMap(rowSteps))).toEqual(source);
  expect(groupPath(tree, "s4")).toEqual([tree[0].key]);
});


it("consolidates instruction-only groups without absorbing actual requests", () => {
  const source = [
    step(0, "System instructions", "system"),
    { ...step(1, "Operating rules", "user"), metadata: { label: { task_id: "t1", intent: "added_context" } } },
    { ...step(2, "Do the work", "user"), metadata: { label: { task_id: "t2", intent: "new_request" } } },
    step(3, "Done"),
    { ...step(4, "Next request", "user"), metadata: { label: { task_id: "t3", intent: "new_request" } } },
  ];
  const snapshot = structuredClone(source);
  const tree = buildTraceOutline(presentTrace(source).rows);
  expect(tree.map((node) => node.rows.map((row) => row.key))).toEqual([["s0", "s1"], ["s2", "s3"], ["s4"]]);
  expect(tree.map(isContextGroup)).toEqual([true, false, false]);
  expect(source).toEqual(snapshot);
});
