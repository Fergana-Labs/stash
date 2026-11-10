import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AnnotationComposer from "./AnnotationComposer";

const evals = [{ id: "e1", name: "DCF memos" }, { id: "e2", name: "Rubric quality" }];
const show = (stepId: string | null, withEvals = evals) => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(<AnnotationComposer target={{ stepId, quote: null }} label="Comment on step 3" evals={withEvals} onCancel={vi.fn()} onSubmit={onSubmit} />);
  return onSubmit;
};

it("comments on a step and adds it to the chosen eval as a bad example", async () => {
  const onSubmit = show("s3");
  fireEvent.change(screen.getByRole("textbox", { name: "Comment on step 3" }), { target: { value: " full of arrows " } });
  // Nothing is added unless an eval is chosen, and the label only appears once one is.
  expect(screen.queryByRole("group", { name: "Example label" })).toBeNull();
  fireEvent.change(screen.getByRole("combobox", { name: "Add to eval" }), { target: { value: "e1" } });
  expect(screen.getByRole("button", { name: "Bad" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Comment and add" }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("full of arrows", { evalId: "e1", label: "bad" }));
});

it("adds a step as a good example, and only comments when no eval is chosen", async () => {
  const onSubmit = show("s3");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "clean prose" } });
  fireEvent.click(screen.getByRole("button", { name: "Comment" }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("clean prose", null));
  fireEvent.change(screen.getByRole("combobox", { name: "Add to eval" }), { target: { value: "e2" } });
  fireEvent.click(screen.getByRole("button", { name: "Good" }));
  fireEvent.click(screen.getByRole("button", { name: "Comment and add" }));
  await waitFor(() => expect(onSubmit).toHaveBeenLastCalledWith("clean prose", { evalId: "e2", label: "good" }));
});

it("offers no eval for a comment on the whole trace, or when the person has no evals", () => {
  const { unmount } = render(<AnnotationComposer target={{ stepId: null, quote: null }} label="Comment" evals={evals} onCancel={vi.fn()} onSubmit={vi.fn()} />);
  expect(screen.queryByRole("combobox", { name: "Add to eval" })).toBeNull();
  unmount();
  show("s3", []);
  expect(screen.queryByRole("combobox", { name: "Add to eval" })).toBeNull();
});
