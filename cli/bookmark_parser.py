"""Netscape Bookmark File Format parser.

Parses Chrome/Firefox exported bookmark .html files into structured data.
Uses Python stdlib html.parser — no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


@dataclass
class Bookmark:
    title: str
    url: str
    add_date: int | None = None
    folder_path: list[str] = field(default_factory=list)

    @property
    def folder_label(self) -> str:
        return " > ".join(self.folder_path) if self.folder_path else "(root)"


class _BookmarkHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks: list[Bookmark] = []
        self._folder_stack: list[str] = []
        self._current_url: str | None = None
        self._current_add_date: int | None = None
        self._current_tag: str | None = None
        self._text_buf: list[str] = []
        self._in_h3 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        self._current_tag = tag
        attr_dict = {k.lower(): v for k, v in attrs}

        if tag == "a":
            self._current_url = attr_dict.get("href")
            add_date = attr_dict.get("add_date")
            self._current_add_date = int(add_date) if add_date and add_date.isdigit() else None
            self._text_buf = []
        elif tag == "h3":
            self._in_h3 = True
            self._text_buf = []
        elif tag == "dl":
            pass  # folder contents start

    def handle_endtag(self, tag: str):
        tag = tag.lower()

        if tag == "a" and self._current_url:
            title = "".join(self._text_buf).strip() or self._current_url
            self.bookmarks.append(Bookmark(
                title=title,
                url=self._current_url,
                add_date=self._current_add_date,
                folder_path=list(self._folder_stack),
            ))
            self._current_url = None
            self._current_add_date = None
            self._text_buf = []
        elif tag == "h3":
            folder_name = "".join(self._text_buf).strip()
            if folder_name:
                self._folder_stack.append(folder_name)
            self._in_h3 = False
            self._text_buf = []
        elif tag == "dl":
            if self._folder_stack:
                self._folder_stack.pop()

        self._current_tag = None

    def handle_data(self, data: str):
        if self._current_tag in ("a", "h3") or self._in_h3:
            self._text_buf.append(data)


def parse_bookmark_file(path: str | Path) -> list[Bookmark]:
    """Parse a Netscape Bookmark File Format .html export.

    Returns a flat list of Bookmark objects with folder_path indicating
    the hierarchy (e.g., ["Bookmarks Bar", "Tech", "AI"]).
    """
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    parser = _BookmarkHTMLParser()
    parser.feed(content)
    return parser.bookmarks


def unique_folders(bookmarks: list[Bookmark]) -> list[str]:
    """Extract unique folder labels from bookmarks, preserving order."""
    seen: set[str] = set()
    folders: list[str] = []
    for b in bookmarks:
        label = b.folder_label
        if label != "(root)" and label not in seen:
            seen.add(label)
            folders.append(label)
    return folders
