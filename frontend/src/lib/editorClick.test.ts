import { describe, expect, it } from "vitest";
import { shouldFocusEditorFrame } from "./editorClick";

describe("shouldFocusEditorFrame", () => {
  it("does not focus the frame for clicks inside editor content", () => {
    const editorElement = document.createElement("div");
    const paragraph = document.createElement("p");
    editorElement.append(paragraph);

    expect(shouldFocusEditorFrame(editorElement, paragraph)).toBe(false);
  });

  it("focuses the editor for clicks on surrounding frame chrome", () => {
    const editorElement = document.createElement("div");
    const frameElement = document.createElement("div");
    frameElement.append(editorElement);

    expect(shouldFocusEditorFrame(editorElement, frameElement)).toBe(true);
  });

  it("ignores targets that cannot contain a cursor position", () => {
    expect(
      shouldFocusEditorFrame(document.createElement("div"), new EventTarget()),
    ).toBe(false);
  });
});
