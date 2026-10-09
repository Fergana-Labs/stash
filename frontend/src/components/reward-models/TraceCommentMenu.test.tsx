import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RmStep } from "@/lib/types";
import AnchoredText from "./AnchoredText";
import TraceCommentMenu from "./TraceCommentMenu";
import { selectedCommentTarget } from "./trace-comment-selection";
import { annotationStepIds, locateQuote, quoteForStep, sortAnnotations } from "./rm-text";
import type { RmAnnotation } from "@/lib/types";

const steps: RmStep[] = ["First **important** message.", "Second message, with more context."].map((content, index) => ({
  id: `s${index}`, index, content, role: "system", tool_name: null, tool_input: null, tool_call_id: null, metadata: null,
}));

function setup() {
  const comment = vi.fn();
  const result = render(<TraceCommentMenu steps={steps} onComment={comment}>
    <div data-testid="canvas">{steps.map((step) => <div key={step.id} data-step-id={step.id}>
      <h3>System {step.index + 1}</h3>
      <AnchoredText stepId={step.id} content={step.content} markdown highlights={[]} onSelectAnnotation={vi.fn()} />
      <button>Read full message</button>
    </div>)}</div>
  </TraceCommentMenu>);
  const canvas = screen.getByTestId("canvas");
  const first = canvas.querySelector("strong [data-o]")!.firstChild!;
  const last = canvas.querySelector('[data-step-content="s1"] [data-o]')!.firstChild!;
  return { ...result, canvas, first, last, comment };
}

function select(start: Node, end: Node, endOffset: number) {
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  const range = document.createRange();
  range.setStart(start, 0);
  range.setEnd(end, endOffset);
  range.getBoundingClientRect = () => ({ left: 20, top: 30, bottom: 45 } as DOMRect);
  selection.addRange(range);
  return selection;
}

afterEach(() => { cleanup(); window.getSelection()?.removeAllRanges(); });

describe("trace comment context menu", () => {
  it("offers a contextual menu on selection and waits for the comment action", async () => {
    const { first, comment } = setup();
    select(first, first, 9);
    fireEvent.mouseUp(first.parentElement!);
    expect(await screen.findByRole("menu")).toBeInTheDocument();
    expect(comment).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("menuitem", { name: "Comment on selection" }));
    expect(comment).toHaveBeenCalledWith({ stepId: "s0", quote: { text: "important", prefix: "First **", suffix: "** message." } });
  });

  it("saves one cross-message quote with independent source anchors and no intervening UI", async () => {
    const { canvas, first, last, comment } = setup();
    const selection = select(first, last, 14);
    const target = selectedCommentTarget(canvas, selection, steps)!;
    expect(target.stepId).toBeNull();
    expect(target.quote?.text).toBe("important** message.\n\nSecond message");
    expect(target.quote?.segments?.map((segment) => segment.step_id)).toEqual(["s0", "s1"]);
    for (const step of steps) expect(locateQuote(step.content, quoteForStep(step.id, target.quote, target.stepId)!)).not.toBeNull();
    fireEvent.mouseUp(last.parentElement!);
    expect(comment).not.toHaveBeenCalled();
    expect(await screen.findByRole("menu")).toBeInTheDocument();
    // Opening the menu may change the browser selection; its snapshot must survive.
    selection.removeAllRanges();
    fireEvent.click(await screen.findByRole("menuitem", { name: "Comment on selection" }));
    expect(comment).toHaveBeenCalledExactlyOnceWith(target);
    const annotation = { id: "multi", step_id: null, quote: target.quote, created_at: "2026-01-01" } as RmAnnotation;
    expect(annotationStepIds(annotation)).toEqual(["s0", "s1"]);
    expect(sortAnnotations([{ ...annotation, id: "later", step_id: "s1", quote: null }, annotation], steps).map((a) => a.id)).toEqual(["multi", "later"]);
  });

  it("supports element boundaries, backward selections, and a collapsed selection", () => {
    const { canvas, first, last } = setup();
    const selection = select(first, last, 6);
    const forward = selectedCommentTarget(canvas, selection, steps);
    selection.setBaseAndExtent(last, 6, first, 0);
    expect(selectedCommentTarget(canvas, selection, steps)).toEqual(forward);
    selection.selectAllChildren(canvas);
    expect(selectedCommentTarget(canvas, selection, steps)?.quote?.segments).toHaveLength(2);
    selection.collapse(first, 0);
    expect(selectedCommentTarget(canvas, selection, steps)).toBeNull();
  });

  it("offers message comments without a selection and dismisses without opening a composer", async () => {
    const { first, comment } = setup();
    fireEvent.contextMenu(first.parentElement!, { clientX: 60, clientY: 80 });
    const item = await screen.findByRole("menuitem", { name: "Comment on message" });
    fireEvent.keyDown(item, { key: "Escape" });
    expect(comment).not.toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens the keyboard context menu when selecting text leaves focus on the document", async () => {
    const { first, last, comment } = setup();
    const selection = select(first, last, 6);
    selection.getRangeAt(0).getBoundingClientRect = () => ({ left: 20, top: 30 } as DOMRect);
    fireEvent.keyDown(document.body, { key: "F10", shiftKey: true });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Comment on selection" }));
    expect(comment.mock.calls[0][0].quote.segments).toHaveLength(2);
  });
});
