export function shouldFocusEditorFrame(
  editorElement: HTMLElement,
  target: EventTarget | null,
): boolean {
  if (!(target instanceof Node)) return false;

  return !editorElement.contains(target);
}
