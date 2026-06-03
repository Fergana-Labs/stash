import { describe, expect, it } from "vitest";
import {
  getEditorFrameFocusPosition,
  shouldFocusEditorFrame,
} from "./editorClick";

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

describe("getEditorFrameFocusPosition", () => {
  it("focuses the start for clicks above the editor body", () => {
    const editorElement = document.createElement("div");
    editorElement.getBoundingClientRect = () =>
      ({ top: 100 }) as DOMRect;

    expect(getEditorFrameFocusPosition(editorElement, 80)).toBe("start");
  });

  it("focuses the end for clicks below the editor body", () => {
    const editorElement = document.createElement("div");
    editorElement.getBoundingClientRect = () =>
      ({ top: 100 }) as DOMRect;

    expect(getEditorFrameFocusPosition(editorElement, 120)).toBe("end");
  });
});
