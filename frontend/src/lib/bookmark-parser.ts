/**
 * Client-side Netscape Bookmark File Format parser.
 * Parses Chrome/Firefox bookmark .html exports using DOMParser.
 */

export interface ParsedBookmark {
  title: string;
  url: string;
  folder: string;
}

export function parseBookmarkHTML(html: string): ParsedBookmark[] {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const bookmarks: ParsedBookmark[] = [];

  function walk(node: Element, folderPath: string[]) {
    for (const child of Array.from(node.children)) {
      if (child.tagName === "DT") {
        const link = child.querySelector(":scope > A");
        const folder = child.querySelector(":scope > H3");
        const dl = child.querySelector(":scope > DL");

        if (link) {
          const href = link.getAttribute("HREF") || link.getAttribute("href");
          if (href && href.startsWith("http")) {
            bookmarks.push({
              title: link.textContent?.trim() || href,
              url: href,
              folder: folderPath.join(" > ") || "(root)",
            });
          }
        }

        if (folder && dl) {
          const folderName = folder.textContent?.trim() || "";
          walk(dl, [...folderPath, folderName]);
        } else if (dl) {
          walk(dl, folderPath);
        }
      } else if (child.tagName === "DL") {
        walk(child, folderPath);
      }
    }
  }

  walk(doc.body, []);
  return bookmarks;
}
