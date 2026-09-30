export function visibleStepElement(container: HTMLElement, navigation: HTMLElement): HTMLElement | null {
  const boundary = navigation.getBoundingClientRect().bottom + 12;
  const elements = [...container.querySelectorAll<HTMLElement>('[id^="step-"]')];
  // The last row may be too short to reach the top beneath the sticky graph.
  const atBottom = container.scrollHeight > container.clientHeight
    && container.scrollHeight - container.scrollTop - container.clientHeight <= 1;
  if (atBottom) elements.reverse();
  for (const element of elements) {
    if (element.getClientRects().length === 0) continue;
    if (element.getBoundingClientRect().bottom > boundary) return element;
  }
  return null;
}
