import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { RefineCurve, gainsExhausted, passLabel } from "./RefinePanel";

const point = (pass: number, acc: number, accepted: boolean, kind?: string) => ({ pass, cv_accuracy: acc, cv_log_loss: null, macro_f1: null, questions: 3, accepted, edits: kind ? [{ kind, question_id: "q", rationale: "" }] : [] });

it("labels kept passes with their edit and marks a plateau", () => {
  const curve = [point(0, 0.6, true), point(1, 0.7, true, "add_criterion"), point(2, 0.68, false, "tighten_wording")];
  expect(passLabel(curve[1])).toBe("Added criterion");
  expect(gainsExhausted(curve, true)).toBe(true);
  expect(gainsExhausted(curve, false)).toBe(false);
  render(<RefineCurve curve={curve} finished />);
  expect(screen.getByText("Added criterion")).toBeInTheDocument();
  expect(screen.queryByText("Tightened wording")).not.toBeInTheDocument();
  expect(screen.getByText("Gains exhausted")).toBeInTheDocument();
});
