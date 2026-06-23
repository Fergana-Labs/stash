import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CommentComposerPopover from "./CommentComposerPopover";

function renderComposer() {
  return render(
    <CommentComposerPopover
      top={10}
      left={20}
      onCancel={vi.fn()}
      onSubmit={vi.fn()}
    />
  );
}

describe("CommentComposerPopover", () => {
  afterEach(() => {
    cleanup();
  });

  it("allows native text selection inside the comment textarea", () => {
    renderComposer();

    const textarea = screen.getByPlaceholderText(/Add a comment/i);

    expect(fireEvent.mouseDown(textarea)).toBe(true);
  });

  it("keeps anchor selection alive when pressing the popover chrome", () => {
    renderComposer();

    const textarea = screen.getByPlaceholderText(/Add a comment/i);
    const popover = textarea.parentElement;

    expect(popover).not.toBeNull();
    expect(fireEvent.mouseDown(popover as HTMLElement)).toBe(false);
  });
});
