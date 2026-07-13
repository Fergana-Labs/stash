"""Parse Netscape-format bookmarks.html exports (Chrome, Firefox, Safari).

The format is nested <DL> lists: <DT><H3> names a folder whose <DL> follows,
<DT><A HREF ADD_DATE> is a bookmark. Real exports routinely omit closing
tags, so this leans on html.parser's tolerance rather than a strict tree.
"""

from html.parser import HTMLParser


def parse_bookmarks(html: str) -> list[dict]:
    """Return [{folder_path: tuple[str, ...], title, url, add_date}].

    Only http(s) URLs survive (drops javascript:, place:, chrome: entries);
    duplicate URLs keep their first occurrence.
    """
    parser = _NetscapeParser()
    parser.feed(html)
    seen: set[str] = set()
    bookmarks = []
    for bookmark in parser.bookmarks:
        url = bookmark["url"]
        if not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        bookmarks.append(bookmark)
    return bookmarks


class _NetscapeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bookmarks: list[dict] = []
        self._folder_stack: list[str] = []
        self._pending_folder: str | None = None
        self._current_link: dict | None = None
        self._capturing: str | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("h3", "a", "dl", "dt"):
            # Exports routinely omit </A>; any structural tag ends the link.
            self._finish_link()
        if tag == "h3":
            self._capturing = "folder"
            self._pending_folder = ""
        elif tag == "a":
            attributes = dict(attrs)
            self._current_link = {
                "url": attributes.get("href") or "",
                "add_date": attributes.get("add_date"),
                "title": "",
            }
            self._capturing = "link"
        elif tag == "dl":
            # A <dl> opens the folder most recently named by an <h3>; the
            # top-level <dl> has none and contributes no path segment.
            self._folder_stack.append(self._pending_folder or "")
            self._pending_folder = None

    def handle_endtag(self, tag: str) -> None:
        if tag in ("a", "dl", "dt"):
            self._finish_link()
        if tag == "h3":
            self._capturing = None
        elif tag == "dl" and self._folder_stack:
            self._folder_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._capturing == "folder" and self._pending_folder is not None:
            self._pending_folder += data
        elif self._capturing == "link" and self._current_link is not None:
            self._current_link["title"] += data

    def _finish_link(self) -> None:
        link = self._current_link
        self._current_link = None
        self._capturing = None
        if not link or not link["url"]:
            return
        self.bookmarks.append(
            {
                "folder_path": tuple(name.strip() for name in self._folder_stack if name.strip()),
                "title": link["title"].strip() or link["url"],
                "url": link["url"],
                "add_date": link["add_date"],
            }
        )
