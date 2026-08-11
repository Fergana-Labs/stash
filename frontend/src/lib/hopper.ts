import type { HopperItem } from "./api";

/** Which drop a piece of typed or pasted text is. A bare URL is a link — we
 *  fetch the page behind it — and everything else is the note it looks like.
 *  Text that merely contains a URL is prose, not a link. */
export function isLinkDrop(text: string): boolean {
  return /^https?:\/\/\S+$/i.test(text.trim());
}

/** Where the drop landed in the app, or null while it is still on its way. */
export function targetHref(item: HopperItem): string | null {
  if (!item.target) return null;
  return item.target.kind === "page" ? `/p/${item.target.id}` : `/f/${item.target.id}`;
}
