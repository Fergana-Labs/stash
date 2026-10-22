import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { RefineCurve, gainsExhausted, passLabel, sameRubric } from "./RefinePanel";

const point = (pass: number, acc: number, accepted: boolean, kind?: string) => ({ pass, cv_accuracy: acc, cv_log_loss: null, macro_f1: null, questions: 3, accepted, edits: kind ? [{ kind, question_id: "q", rationale: "" }] : [] });

it("names each pass by its edit and marks a plateau", () => {
  const curve = [point(0, 0.6, true), point(1, 0.7, true, "add_criterion"), point(2, 0.68, false, "tighten_wording")];
  expect(passLabel(curve[1])).toBe("Added criterion");
  expect(gainsExhausted(curve, true)).toBe(true);
  expect(gainsExhausted(curve, false)).toBe(false);
  const { container } = render(<RefineCurve curve={curve} finished />);
  const titles = [...container.querySelectorAll("title")].map((t) => t.textContent);
  expect(titles).toContain("Pass 1, Added criterion, accuracy 70%, kept");
  expect(titles).toContain("Pass 2, Tightened wording, accuracy 68%, rejected");
  expect(screen.getByText("Gains exhausted")).toBeInTheDocument();
});

it("treats a saved rubric as the same despite key order and dropped nulls", () => {
  expect(sameRubric([{ id: "a", prompt: "p", eval_id: null }], [{ prompt: "p", id: "a" }])).toBe(true);
  expect(sameRubric([{ id: "a", prompt: "p" }], [{ id: "a", prompt: "q" }])).toBe(false);
  // A retrain re-adds the verdict and probe in its own order with a new probe version.
  expect(sameRubric(
    [{ id: "a", prompt: "p" }, { id: "verdict", type: "choice" }, { id: "embedding_probe", type: "probe", version_id: "1" }],
    [{ id: "a", prompt: "p" }, { id: "embedding_probe", type: "probe", version_id: "2" }, { id: "verdict", type: "choice" }],
  )).toBe(true);
});
