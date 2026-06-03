export function shouldFocusEditorFrame(
  editorElement: HTMLElement,
  target: EventTarget | null,
): boolean {
  if (!(target instanceof Node)) return false;

  return !editorElement.contains(target);
}

export type EditorFrameFocusPosition = "start" | "end";

export function getEditorFrameFocusPosition(
  editorElement: HTMLElement,
  clickY: number,
): EditorFrameFocusPosition {
  const { top } = editorElement.getBoundingClientRect();

  return clickY < top ? "start" : "end";
}
