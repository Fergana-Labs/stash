// Client-side comment-anchor highlighting. Anchors are stored as quoted
// text (never written into the page content, which is token-protected),
// so highlighting means finding the quote in the rendered DOM and
// wrapping it in a `[data-comment-id]` span — the same marker the app
// styles. Quotes that no longer appear verbatim (the text was edited
// away) silently don't highlight.

export type QuoteHighlight = { id: string; quoted: string };

export function highlightQuotes(root: HTMLElement, items: QuoteHighlight[]): void {
  for (const item of items) {
    if (!item.quoted) continue;
    if (root.querySelector(`[data-comment-id="${CSS.escape(item.id)}"]`)) continue;
    wrapFirstMatch(root, item.quoted, item.id);
  }
}

function wrapFirstMatch(root: HTMLElement, quoted: string, id: string): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  const starts: number[] = [];
  let full = "";
  let node: Node | null;
  while ((node = walker.nextNode())) {
    starts.push(full.length);
    nodes.push(node as Text);
    full += node.textContent ?? "";
  }
  const idx = full.indexOf(quoted);
  if (idx < 0) return;

  const start = locate(nodes, starts, idx, false);
  const end = locate(nodes, starts, idx + quoted.length, true);
  if (!start || !end) return;

  const range = document.createRange();
  range.setStart(start.node, start.offset);
  range.setEnd(end.node, end.offset);
  const mark = document.createElement("span");
  mark.setAttribute("data-comment-id", id);
  // surroundContents throws when the range spans partial element
  // boundaries — fall back to extracting + reinserting, like the app.
  try {
    range.surroundContents(mark);
  } catch {
    mark.appendChild(range.extractContents());
    range.insertNode(mark);
  }
}

function locate(
  nodes: Text[],
  starts: number[],
  pos: number,
  isEnd: boolean,
): { node: Text; offset: number } | null {
  // For an end position, the owning node is the one containing pos-1 —
  // an end offset equal to a node's length is valid for ranges.
  const probe = isEnd ? pos - 1 : pos;
  for (let i = nodes.length - 1; i >= 0; i--) {
    if (starts[i] <= probe) return { node: nodes[i], offset: pos - starts[i] };
  }
  return null;
}
