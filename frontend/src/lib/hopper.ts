/** Which drop a piece of typed or pasted text is. A bare URL is a link — we
 *  fetch the page behind it — and everything else is the note it looks like.
 *  Text that merely contains a URL is prose, not a link. */
export function isLinkDrop(text: string): boolean {
  return /^https?:\/\/\S+$/i.test(text.trim());
}

/** The URL a drag carries. `text/uri-list` is a list format: CRLF-separated,
 *  with `#` comment lines — taking it whole meant a dragged tab could be
 *  rejected as "not a link". */
export function firstUrlFromDrag(uriList: string): string {
  const line = uriList
    .split(/\r?\n/)
    .map((l) => l.trim())
    .find((l) => l && !l.startsWith("#"));
  return line ?? "";
}
