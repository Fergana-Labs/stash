"""Read-only virtual filesystem model over Stash, backing the `stash vfs` shell."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import stat
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .client import StashClient, StashError

BytesLoader = Callable[[], bytes]

# Hard ceiling on entries materialized per source. A source bigger than this
# gets a truncation warning from the listing commands rather than an
# ever-growing tree walk.
SOURCE_ENTRIES_MAX = 10_000


class MountError(Exception):
    pass


@dataclass
class VfsNode:
    path: str
    mode: int
    loader: BytesLoader | None = None
    content: bytes | None = None
    size_hint: int | None = None
    children: dict[str, str] = field(default_factory=dict)
    created_at: float | None = None
    updated_at: float | None = None
    # Provider-side id of a connected-source document (a Drive file id, a Gmail
    # message id, …), so `stat` can tie a VFS path back to the provider object.
    external_ref: str | None = None

    @property
    def is_dir(self) -> bool:
        return stat.S_ISDIR(self.mode)

    @property
    def is_file(self) -> bool:
        return stat.S_ISREG(self.mode)


class StashVfsModel:
    def __init__(self, client: StashClient):
        self.client = client
        self.nodes: dict[str, VfsNode] = {}
        # Source-root path -> thunk that fetches that source's entries. A source's
        # contents are materialized only when something first descends into it, so
        # listing source names stays cheap no matter how large the source is.
        self._expanders: dict[str, Callable[[], None]] = {}
        # Source-root path -> entries shown, for sources the server truncated.
        # Lets listing commands warn that the tree is incomplete.
        self._truncated: dict[str, int] = {}

    def refresh(self) -> None:
        self.nodes = {}
        self._expanders = {}
        self._truncated = {}
        self._add_dir("/")
        self._add_root()
        self._add_static_file(
            "/README.md",
            "\n".join(
                [
                    "# Stash",
                    "",
                    "This is a read-only virtual filesystem view over Stash.",
                    "",
                    "- `files` exposes folders, pages, and uploaded files.",
                    "- `memory` is the agent-curated Memory wiki (stored separately from `files`).",
                    "- Sessions, skills, and tables are read-only projections.",
                    "- `sources` exposes connected integrations (Gmail, "
                    "GitHub, Slack, Jira, …) as read-only documents.",
                    "- `computer` is a live, read-only view of your cloud "
                    "computer's disk (browsing may wake it).",
                    "",
                    "Listings are alphabetical by name; they carry no time meaning.",
                    "For recency use `ls -lt` (sort by modified time), "
                    "`find -mtime -N` / `find -newer <path>`, or `stat <path>`.",
                    "Slack renders as one transcript per channel per UTC day; a "
                    "`0000-history-cap` entry in a channel means older history "
                    "exists in Slack but is not indexed here.",
                    "",
                ]
            ),
        )

    def exists(self, path: str) -> bool:
        path = self._clean_path(path)
        self._ensure_expanded(path)
        return path in self.nodes

    def list_dir(self, path: str) -> list[str]:
        node = self._get_node(path)
        if not node.is_dir:
            raise NotADirectoryError(path)
        return sorted(node.children)

    def read_file(self, path: str) -> bytes:
        node = self._get_node(path)
        if not node.is_file:
            raise IsADirectoryError(path)
        if node.content is None:
            if node.loader is None:
                node.content = b""
            else:
                node.content = node.loader()
                node.size_hint = len(node.content)
        return node.content

    def getattr(self, path: str) -> dict:
        node = self._get_node(path)
        size = node.size_hint
        if size is None and node.content is not None:
            size = len(node.content)

        now = time.time()
        return {
            "st_mode": node.mode,
            "st_nlink": 2 if node.is_dir else 1,
            "st_ino": _inode_for_path(node.path),
            "st_uid": os.getuid(),
            "st_gid": os.getgid(),
            "st_size": size or 0,
            "st_ctime": node.created_at or 0.0,
            "st_mtime": node.updated_at or 0.0,
            "st_atime": now,
        }

    def _add_root(self) -> None:
        overview = self.client.get_overview()
        memory_folder_id = str(self.client.get_memory_folder()["id"])

        self._add_files_tree(overview.get("files", {}), memory_folder_id)
        self._add_skills(overview.get("skills", []))
        self._add_sessions(overview.get("sessions", []))
        self._add_tables()
        self._add_sources()
        self._add_computer()

    def _add_computer(self) -> None:
        """The user's cloud computer, projected read-through at /computer.

        Directories expand lazily one level at a time (a workspace can hold a
        cloned repo — materializing the whole tree would be pathological), and
        file bodies load on read. Nothing is cached server-side; every descent
        is a live look at the machine."""
        root = self._add_dir("/computer")
        self._expanders[root] = lambda: self._expand_computer_dir(root, "")

    def _expand_computer_dir(self, dir_path: str, rel_path: str) -> None:
        try:
            entries = self.client.machine_fs_list(rel_path)
        except StashError:
            return
        for entry in entries:
            child_rel = f"{rel_path}/{entry['name']}" if rel_path else entry["name"]
            if entry["dir"]:
                child = self._add_dir_child(dir_path, entry["name"])
                self._expanders[child] = lambda c=child, r=child_rel: self._expand_computer_dir(
                    c, r
                )
            else:
                self._add_file(
                    f"{dir_path}/{entry['name']}",
                    loader=lambda r=child_rel: self.client.machine_fs_read(r),
                    size_hint=entry.get("size"),
                )

    def _add_files_tree(self, tree: dict, memory_folder_id: str) -> None:
        root_path = "/files"
        self._add_dir(root_path)
        # The Memory wiki is stored as a reserved folder in the files tree but
        # presented as its own root — /files and /memory are MECE, mirroring
        # the app Explorer's sections.
        self._add_dir("/memory")
        folders = {str(folder["id"]): folder for folder in tree.get("folders", [])}
        pages = tree.get("pages", [])
        # Files embedded in a page are internals of that document, not tree
        # entries — the overview omits them. The page's markdown links them by
        # download URL and `stash files download` fetches the bytes.
        files = tree.get("files", [])
        ambiguous = _files_ambiguity(folders.values(), pages, files)
        folder_paths: dict[str, str] = {}

        def siblings(parent_id) -> set[str]:
            return ambiguous.get(str(parent_id or ""), set())

        def folder_path(folder_id: str) -> str:
            if folder_id in folder_paths:
                return folder_paths[folder_id]
            if folder_id == memory_folder_id:
                folder_paths[folder_id] = "/memory"
                return "/memory"
            folder = folders[folder_id]
            parent_id = folder.get("parent_folder_id")
            parent_path = folder_path(str(parent_id)) if parent_id else root_path
            name = _dir_display_name(folder.get("name") or "folder", folder_id, siblings(parent_id))
            path = self._add_dir_child(
                parent_path,
                name,
                created_at=folder.get("created_at"),
                updated_at=folder.get("updated_at"),
            )
            folder_paths[folder_id] = path
            return path

        for folder_id in folders:
            folder_path(folder_id)

        for page in pages:
            page_id = str(page["id"])
            parent_id = page.get("folder_id")
            parent_path = folder_path(str(parent_id)) if parent_id else root_path
            name = _file_display_name(
                page.get("name") or "page", page_id, _page_extension(page), siblings(parent_id)
            )
            self._add_file(
                f"{parent_path}/{name}",
                loader=lambda pid=page_id: self._load_page(pid),
                created_at=page.get("created_at"),
                updated_at=page.get("updated_at"),
            )

        for file in files:
            file_id = str(file["id"])
            parent_id = file.get("folder_id")
            parent_path = folder_path(str(parent_id)) if parent_id else root_path
            name = _file_display_name(file.get("name") or "file", file_id, "", siblings(parent_id))
            # Uploaded files are immutable — there is no separate update event,
            # so the file's last-modified time is its creation time.
            created_at = file.get("created_at")
            self._add_file(
                f"{parent_path}/{name}",
                loader=lambda fid=file_id: self.client.download_file(fid),
                size_hint=file.get("size_bytes"),
                created_at=created_at,
                updated_at=created_at,
            )

    def _add_skills(self, skills: list[dict]) -> None:
        skills_path = "/skills"
        self._add_dir(skills_path)
        self._add_jsonl_file(f"{skills_path}/_index.jsonl", skills)
        published = [skill for skill in skills if skill.get("folder_id")]
        ambiguous = _ambiguous_basenames(
            [_safe_name(skill.get("name") or "skill") for skill in published]
        )
        for skill in published:
            folder_id = str(skill["folder_id"])
            basename = _dir_display_name(skill.get("name") or "skill", folder_id, ambiguous)
            self._add_json_file(f"{skills_path}/{basename}.json", skill)
            slug = (skill.get("published") or {}).get("slug")
            if slug:
                self._add_file(
                    f"{skills_path}/{basename}.md",
                    loader=lambda s=slug: _text_bytes(self.client.get_skill_text(s)),
                )

    def _add_sessions(self, sessions: list[dict]) -> None:
        sessions_path = "/sessions"
        self._add_dir(sessions_path)
        self._add_jsonl_file(f"{sessions_path}/_index.jsonl", sessions)
        ambiguous = _ambiguous_basenames(
            [_safe_name(session.get("title") or str(session["session_id"])) for session in sessions]
        )
        for session in sessions:
            session_id = str(session["session_id"])
            row_id = str(session.get("id") or session_id)
            updated_at = session.get("updated_at")
            name = _dir_display_name(session.get("title") or session_id, row_id, ambiguous)
            session_path = self._add_dir_child(sessions_path, name, updated_at=updated_at)
            self._add_json_file(f"{session_path}/metadata.json", session, updated_at=updated_at)
            self._add_file(
                f"{session_path}/events.json",
                loader=lambda sid=session_id: _json_bytes(
                    {"events": self.client.get_transcript_events(sid)}
                ),
                updated_at=updated_at,
            )
            self._add_file(
                f"{session_path}/transcript.jsonl",
                loader=lambda sid=session_id: _text_bytes(self.client.export_transcript_jsonl(sid)),
                updated_at=updated_at,
            )
            self._add_file(
                f"{session_path}/transcript.md",
                loader=lambda sid=session_id: _text_bytes(
                    _session_markdown(self.client.get_transcript_events(sid))
                ),
                updated_at=updated_at,
            )

    def _add_tables(self) -> None:
        tables_path = "/tables"
        self._add_dir(tables_path)
        tables = self.client.list_tables()
        self._add_jsonl_file(f"{tables_path}/_index.jsonl", tables)
        ambiguous = _ambiguous_basenames(
            [_safe_name(table.get("name") or "table") for table in tables]
        )
        for table in tables:
            table_id = str(table["id"])
            created_at = table.get("created_at")
            updated_at = table.get("updated_at")
            name = _dir_display_name(table.get("name") or "table", table_id, ambiguous)
            table_path = self._add_dir_child(
                tables_path,
                name,
                created_at=created_at,
                updated_at=updated_at,
            )
            self._add_file(
                f"{table_path}/schema.json",
                loader=lambda tid=table_id: _json_bytes(self.client.get_table(tid)),
                created_at=created_at,
                updated_at=updated_at,
            )
            self._add_file(
                f"{table_path}/rows.json",
                loader=lambda tid=table_id: _json_bytes(self._load_all_table_rows(tid)),
                created_at=created_at,
                updated_at=updated_at,
            )
            self._add_file(
                f"{table_path}/rows.jsonl",
                loader=lambda tid=table_id: _jsonl_bytes(
                    self._load_all_table_rows(tid).get("rows", [])
                ),
                created_at=created_at,
                updated_at=updated_at,
            )

    def _add_sources(self) -> None:
        """Expose connected integrations (Gmail, GitHub, Slack, Jira, …) as
        read-only document trees. Native files/sessions are already mounted
        above, so skip them. Each source's full entry list is materialized;
        document bodies load lazily on read."""
        try:
            sources = self.client.list_sources()
        except StashError:
            return
        connected = [s for s in sources if not str(s.get("type", "")).startswith("native_")]
        if not connected:
            return

        sources_path = self._add_dir("/sources")
        for provider, members in _group_by_provider(connected).items():
            provider_root = self._add_dir_child(sources_path, _source_slug(provider))
            if len(members) == 1:
                # Sole connection collapses — its documents sit directly in the
                # provider folder (e.g. /sources/granola/<call>).
                handle = str(members[0].get("source") or "")
                self._expanders[provider_root] = lambda root=provider_root, h=handle: (
                    self._expand_source(root, h)
                )
                continue
            for member in members:
                handle = str(member.get("source") or "")
                member_root = self._add_dir_child(
                    provider_root, _source_slug(member.get("display_name") or handle)
                )
                self._expanders[member_root] = lambda root=member_root, h=handle: (
                    self._expand_source(root, h)
                )

    def _expand_source(self, source_root: str, handle: str) -> None:
        entries: list[dict] = []
        after = ""
        while True:
            try:
                page, truncated = self.client.list_source_entries_page(handle, "", after=after)
            except StashError:
                break
            entries.extend(page)
            if not truncated:
                break
            after = str(page[-1].get("path") or "")
            if not after or len(entries) >= SOURCE_ENTRIES_MAX:
                # No cursor to continue from (a listing that isn't path-keyed),
                # or the source is beyond what we'll materialize in one tree.
                self._truncated[source_root] = len(entries)
                break
        self._add_source_entries(source_root, handle, entries)

    def truncated_roots_under(self, root: str) -> list[tuple[str, int]]:
        """Truncated source roots overlapping `root` (root contains the source,
        or sits inside it). For subtree enumeration (find/tree): any overlap
        means the enumeration is incomplete. Returns (source_root, shown) pairs."""
        return sorted(
            (s, shown)
            for s, shown in self._truncated.items()
            if s == root or s.startswith(root.rstrip("/") + "/") or root.startswith(s + "/")
        )

    def truncated_root_containing(self, path: str) -> tuple[str, int] | None:
        """The truncated source root that CONTAINS `path` (path is at or below
        it), or None. For single-directory listing (ls): an ancestor like
        /sources — whose own children are complete — must not match, so this is
        narrower than truncated_roots_under."""
        for s, shown in self._truncated.items():
            if path == s or path.startswith(s + "/"):
                return s, shown
        return None

    def _add_source_entries(self, source_root: str, handle: str, entries: list[dict]) -> None:
        parent_refs = _ancestor_refs(entries)
        aliases: list[tuple[str, str]] = []
        for entry in entries:
            ref = str(entry.get("path") or "")
            segments = [_safe_name(seg) for seg in ref.split("/") if seg]
            if not segments:
                continue
            parent = source_root
            for segment in segments[:-1]:
                parent = self._add_dir(f"{parent}/{segment}")
            display = _safe_name(entry.get("name") or segments[-1])
            if entry.get("kind") == "folder":
                self._add_dir(f"{parent}/{display}")
                continue
            # A page that also has child pages becomes a directory holding its own
            # body in a same-named index file, so the children nest under it
            # instead of being dropped on the file/dir name collision.
            if ref in parent_refs:
                page_dir = self._add_dir(f"{parent}/{display}")
                added = self._add_source_doc_file(f"{page_dir}/{display}", handle, ref, entry)
            else:
                added = self._add_source_doc_file(f"{parent}/{display}", handle, ref, entry)
            aliases.append((f"{source_root}/{ref}", added))
        # The backend ref is what search results and history responses hand the
        # agent — make it resolve too. Registered after all real entries so an
        # alias can never shadow a real path; a ref that IS the display path
        # (identical name) is simply already present.
        for alias, target in aliases:
            alias = self._clean_path(alias)
            if alias not in self.nodes:
                self.nodes[alias] = self.nodes[target]

    def _add_source_doc_file(self, path: str, handle: str, ref: str, entry: dict) -> str:
        return self._add_file(
            path,
            loader=lambda h=handle, r=ref: _text_bytes(
                _source_doc_text(self.client.read_source_doc(h, r))
            ),
            size_hint=entry.get("size"),
            updated_at=entry.get("external_updated_at"),
            external_ref=entry.get("external_ref") or None,
        )

    def _load_page(self, page_id: str) -> bytes:
        page = self.client.get_page(page_id)
        if page.get("content_type") == "html":
            return _text_bytes(page.get("content_html") or "")
        return _text_bytes(page.get("content_markdown") or "")

    def _load_all_table_rows(self, table_id: str) -> dict:
        limit = 1000
        offset = 0
        rows: list[dict] = []
        total_count = 0
        while True:
            page = self.client.list_table_rows(table_id, limit=limit, offset=offset)
            page_rows = page.get("rows", [])
            rows.extend(page_rows)
            total_count = int(page.get("total_count", len(rows)))
            if not page.get("has_more"):
                break
            offset += limit
        return {"rows": rows, "total_count": total_count}

    def _add_dir(
        self,
        path: str,
        *,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> str:
        path = self._clean_path(path)
        if path in self.nodes:
            return path
        self.nodes[path] = VfsNode(
            path=path,
            mode=stat.S_IFDIR | 0o755,
            created_at=_parse_iso(created_at),
            updated_at=_parse_iso(updated_at),
        )
        if path != "/":
            parent, name = self._split_parent(path)
            self.nodes[parent].children[name] = path
        return path

    def _add_dir_child(
        self,
        parent: str,
        name: str,
        *,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> str:
        name = self._unique_child_name(parent, name)
        return self._add_dir(f"{parent}/{name}", created_at=created_at, updated_at=updated_at)

    def _add_file(
        self,
        path: str,
        *,
        loader: BytesLoader | None = None,
        content: bytes | None = None,
        size_hint: int | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        external_ref: str | None = None,
    ) -> str:
        path = self._clean_path(path)
        parent, requested_name = self._split_parent(path)
        name = self._unique_child_name(parent, requested_name)
        path = f"{parent}/{name}" if parent != "/" else f"/{name}"
        self.nodes[path] = VfsNode(
            path=path,
            mode=stat.S_IFREG | 0o444,
            loader=loader,
            content=content,
            size_hint=(
                size_hint
                if size_hint is not None
                else (len(content) if content is not None else None)
            ),
            created_at=_parse_iso(created_at),
            updated_at=_parse_iso(updated_at),
            external_ref=external_ref,
        )
        self.nodes[parent].children[name] = path
        return path

    def _add_static_file(self, path: str, content: str) -> str:
        return self._add_file(path, content=_text_bytes(content))

    def _add_json_file(self, path: str, payload: dict, *, updated_at: str | None = None) -> str:
        return self._add_file(path, content=_json_bytes(payload), updated_at=updated_at)

    def _add_jsonl_file(self, path: str, rows: list[dict]) -> str:
        return self._add_file(path, content=_jsonl_bytes(rows))

    def _get_node(self, path: str) -> VfsNode:
        path = self._clean_path(path)
        self._ensure_expanded(path)
        node = self.nodes.get(path)
        if node is None:
            raise FileNotFoundError(path)
        return node

    def _ensure_expanded(self, path: str) -> None:
        """Materialize any lazy subtree containing `path`. No-op once expanded,
        and never triggered by listing the parent directory itself — only by
        descending. Loops because expanding a level can register deeper lazy
        levels (the /computer tree expands one directory at a time)."""
        while True:
            fired = False
            for root in list(self._expanders):
                if path == root or path.startswith(f"{root}/"):
                    self._expanders.pop(root)()
                    fired = True
            if not fired:
                return

    def _unique_child_name(self, parent: str, name: str) -> str:
        existing = self.nodes[parent].children
        if name not in existing:
            return name
        stem, extension = posixpath.splitext(name)
        counter = 2
        while True:
            candidate = f"{stem}-{counter}{extension}"
            if candidate not in existing:
                return candidate
            counter += 1

    @staticmethod
    def _clean_path(path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        clean = posixpath.normpath(path)
        return "/" if clean == "." else clean

    @staticmethod
    def _split_parent(path: str) -> tuple[str, str]:
        parent = posixpath.dirname(path) or "/"
        name = posixpath.basename(path)
        return parent, name


def _inode_for_path(path: str) -> int:
    if path == "/":
        return 1
    digest = hashlib.sha256(path.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _safe_name(value: str) -> str:
    value = re.sub(r"[\x00/\\:]", "-", value.strip())
    value = re.sub(r"\s+", " ", value)
    value = value.strip(". ")
    return (value or "untitled")[:96]


def _source_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-")
    return slug or "source"


def _ancestor_refs(entries: list[dict]) -> set[str]:
    """Refs that are an ancestor of some other entry — i.e. pages that have
    child pages. Such a page renders as a directory so its children nest under
    it instead of colliding with it on the same path."""
    refs: set[str] = set()
    for entry in entries:
        parts = [p for p in str(entry.get("path") or "").split("/") if p]
        for depth in range(1, len(parts)):
            refs.add("/".join(parts[:depth]))
    return refs


def _group_by_provider(connected: list[dict]) -> dict[str, list[dict]]:
    """Connected sources grouped under their provider key, the top tier of the
    /sources filesystem. Sources with no handle are dropped."""
    groups: dict[str, list[dict]] = {}
    for source in connected:
        if not source.get("source"):
            continue
        groups.setdefault(str(source.get("provider") or "source"), []).append(source)
    return groups


def _source_doc_text(doc: dict) -> str:
    return doc.get("content") or doc.get("transcript") or ""


def _ambiguous_basenames(names: list[str]) -> set[str]:
    """Display names that occur more than once in a directory. Only these get an
    id suffix; unique names render clean. Every member of a colliding name is
    suffixed (not just the later ones), so a path never depends on listing order."""
    counts = Counter(names)
    return {name for name, count in counts.items() if count > 1}


def _dir_display_name(name: str, object_id: str, ambiguous: set[str]) -> str:
    base = _safe_name(name)
    return f"{base}--{object_id[:8]}" if base in ambiguous else base


def _split_filename(name: str, default_extension: str) -> tuple[str, str]:
    stem, extension = posixpath.splitext(_safe_name(name))
    return stem or "untitled", extension or default_extension


def _file_display_name(
    name: str, object_id: str, default_extension: str, ambiguous: set[str]
) -> str:
    stem, extension = _split_filename(name, default_extension)
    if f"{stem}{extension}" in ambiguous:
        return f"{stem}--{object_id[:8]}{extension}"
    return f"{stem}{extension}"


def _page_extension(page: dict) -> str:
    return ".html" if (page.get("content_type") or "markdown") == "html" else ".md"


def _files_ambiguity(folders, pages: list[dict], files: list[dict]) -> dict[str, set[str]]:
    """Map each parent folder (keyed by id, "" for root) to the set of colliding
    display names among its folders, pages, and uploaded files combined — paths
    in one directory must be unique across all three kinds."""
    by_parent: dict[str, list[str]] = {}

    def record(parent_id, base: str) -> None:
        by_parent.setdefault(str(parent_id or ""), []).append(base)

    for folder in folders:
        record(folder.get("parent_folder_id"), _safe_name(folder.get("name") or "folder"))
    for page in pages:
        stem, extension = _split_filename(page.get("name") or "page", _page_extension(page))
        record(page.get("folder_id"), f"{stem}{extension}")
    for file in files:
        stem, extension = _split_filename(file.get("name") or "file", "")
        record(file.get("folder_id"), f"{stem}{extension}")
    return {parent: _ambiguous_basenames(names) for parent, names in by_parent.items()}


def _parse_iso(value: str | None) -> float | None:
    """ISO-8601 timestamp from the backend → epoch seconds. None when the
    backend doesn't carry a timestamp for this node (e.g. synthetic dirs)."""
    if not value:
        return None
    return datetime.fromisoformat(value).timestamp()


def _text_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _json_bytes(payload: dict) -> bytes:
    return _text_bytes(f"{json.dumps(payload, indent=2, sort_keys=True, default=str)}\n")


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return _text_bytes("".join(f"{json.dumps(row, sort_keys=True, default=str)}\n" for row in rows))


def _session_markdown(events: list[dict]) -> str:
    if not events:
        return "_No events in this session._\n"
    parts: list[str] = []
    for event in events:
        role = event.get("role") or event.get("event_type") or "event"
        created_at = event.get("created_at") or ""
        tool_name = event.get("tool_name")
        heading = f"## {role}"
        if tool_name:
            heading += f" `{tool_name}`"
        if created_at:
            heading += f" - {created_at}"
        parts.append(heading)
        content = (event.get("content") or "").strip()
        if content:
            parts.append(content)
        parts.append("")
    return "\n".join(parts)
