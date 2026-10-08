import { describe, expect, it } from "vitest";
import type { RmStep } from "@/lib/types";
import { buildRows } from "./trace-rows";
import { traceScrollMarkers, visibleStepElement } from "./trace-scroll";

function step(index: number, role: RmStep["role"], content: string, extra: Partial<RmStep> = {}): RmStep {
  return { id: `s${index}`, index, role, content, tool_name: null, tool_input: null, tool_call_id: null, metadata: null, ...extra };
}

const steps = [
  step(0, "user", "Run the tests"),
  step(1, "assistant", "I should inspect the test setup first.", { metadata: { thinking: true } }),
  step(2, "assistant", "", { tool_name: "exec_command", tool_input: { cmd: "pytest -q" }, tool_call_id: "t1" }),
  step(3, "tool", "44 passed", { tool_call_id: "t1" }),
  step(4, "assistant", "All 44 tests passed."),
  step(5, "user", "Check the next change"),
  step(6, "assistant", "I need to inspect it.", { metadata: { thinking: true } }),
];

describe("traceScrollMarkers", () => {
  it("previews the response after thinking and tools, leaving unanswered turns blank", () => {
    const markers = traceScrollMarkers(buildRows(steps));
    expect(markers.map(({ targetId, preview }) => ({ targetId, preview }))).toEqual([
      { targetId: "step-s0", preview: "All 44 tests passed." },
      { targetId: "step-s5", preview: "" },
    ]);
  });

  it("keeps action destinations in single-request traces and labels thinking explicitly", () => {
    const markers = traceScrollMarkers(buildRows(steps.slice(0, 5)));
    expect(markers.map((marker) => marker.targetId)).toEqual(["step-s0", "step-s1", "step-s2", "step-s4"]);
    expect(markers[0]).toMatchObject({ title: "Run the tests", preview: "All 44 tests passed." });
    expect(markers[1].title).toBe("Thinking");
    expect(markers[2].preview).toBe("pytest -q");
  });

  it("can retain every step when follow-up exchanges belong to one global task", () => {
    expect(traceScrollMarkers(buildRows(steps), true).map((marker) => marker.targetId)).toEqual([
      "step-s0", "step-s1", "step-s2", "step-s4", "step-s5", "step-s6",
    ]);
  });

  it("preserves tool-only navigation without borrowing an answer from another turn", () => {
    expect(traceScrollMarkers(buildRows(steps).filter((row) => row.kind === "tool"))).toEqual([
      { targetId: "step-s2", title: "Exec command", preview: "pytest -q", label: "Step 3", emphasis: false },
    ]);
    const markers = traceScrollMarkers(buildRows([...steps.slice(0, 2), ...steps.slice(5), step(7, "assistant", "The next change is ready.")]));
    expect(markers.map((marker) => marker.preview)).toEqual(["", "The next change is ready."]);
  });
});

it("selects the exact anchor at the navigation boundary, including nested tool results", () => {
  const container = document.createElement("div");
  container.getBoundingClientRect = () => ({ top: 100 }) as DOMRect;
  const navigation = document.createElement("div");
  navigation.getBoundingClientRect = () => ({ bottom: 100 }) as DOMRect;
  container.innerHTML = '<div id="step-16"><div id="step-17"></div></div><div id="step-18"></div>';
  for (const [index, element] of [...container.querySelectorAll<HTMLElement>("[id]")].entries()) {
    const rect = { top: [60, 112, 250][index], bottom: 400 } as DOMRect;
    element.getBoundingClientRect = () => rect;
    element.getClientRects = () => [rect] as unknown as DOMRectList;
  }
  expect(visibleStepElement(container, navigation)?.id).toBe("step-17");
});
