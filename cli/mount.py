"""Read-only virtual filesystem model over Stash, backing the `stash vfs` shell."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .client import StashClient, StashError

BytesLoader = Callable[[], bytes]


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

    def refresh(self) -> None:
        self.nodes = {}
        self._expanders = {}
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
                    "- Sessions, skills, and tables are read-only projections.",
                    "- `sources` exposes connected integrations (Gmail, "
                    "GitHub, Slack, Jira, …) as read-only documents.",
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

        self._add_files_tree(overview.get("files", {}))
        self._add_skills(overview.get("skills", []))
        self._add_sessions(overview.get("sessions", []))
        self._add_tables()
        self._add_sources()

    def _add_files_tree(self, tree: dict) -> None:
        root_path = "/files"
        self._add_dir(root_path)
        folders = {str(folder["id"]): folder for folder in tree.get("folders", [])}
        folder_paths: dict[str, str] = {}

        def folder_path(folder_id: str) -> str:
            if folder_id in folder_paths:
                return folder_paths[folder_id]
            folder = folders[folder_id]
            parent_id = folder.get("parent_folder_id")
            parent_path = folder_path(str(parent_id)) if parent_id else root_path
            path = self._add_dir_child(
                parent_path,
                _object_dir_name(folder.get("name") or "folder", folder_id),
                created_at=folder.get("created_at"),
                updated_at=folder.get("updated_at"),
            )
            folder_paths[folder_id] = path
            return path

        for folder_id in folders:
            folder_path(folder_id)

        for page in tree.get("pages", []):
            page_id = str(page["id"])
            parent_path = (
                folder_path(str(page["folder_id"])) if page.get("folder_id") else root_path
            )
            content_type = page.get("content_type") or "markdown"
            extension = ".html" if content_type == "html" else ".md"
            name = _object_file_name(page.get("name") or "page", page_id, extension)
            self._add_file(
                f"{parent_path}/{name}",
                loader=lambda pid=page_id: self._load_page(pid),
                created_at=page.get("created_at"),
                updated_at=page.get("updated_at"),
            )

        for file in tree.get("files", []):
            file_id = str(file["id"])
            parent_path = (
                folder_path(str(file["folder_id"])) if file.get("folder_id") else root_path
            )
            name = _object_file_name(file.get("name") or "file", file_id, "")
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
        for skill in skills:
            folder_id = str(skill.get("folder_id") or "")
            if not folder_id:
                continue
            basename = _object_basename(skill.get("name") or "skill", folder_id)
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
        for session in sessions:
            session_id = str(session["session_id"])
            row_id = str(session.get("id") or session_id)
            updated_at = session.get("updated_at")
            session_path = self._add_dir_child(
                sessions_path,
                _object_dir_name(session.get("title") or session_id, row_id),
                updated_at=updated_at,
            )
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
        for table in tables:
            table_id = str(table["id"])
            created_at = table.get("created_at")
            updated_at = table.get("updated_at")
            table_path = self._add_dir_child(
                tables_path,
                _object_dir_name(table.get("name") or "table", table_id),
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
                self._expanders[provider_root] = (
                    lambda root=provider_root, h=handle: self._expand_source(root, h)
                )
                continue
            for member in members:
                handle = str(member.get("source") or "")
                member_root = self._add_dir_child(
                    provider_root, _source_slug(member.get("display_name") or handle)
                )
                self._expanders[member_root] = (
                    lambda root=member_root, h=handle: self._expand_source(root, h)
                )

    def _expand_source(self, source_root: str, handle: str) -> None:
        try:
            entries = self.client.list_source_entries(handle, "")
        except StashError:
            return
        self._add_source_entries(source_root, handle, entries)

    def _add_source_entries(self, source_root: str, handle: str, entries: list[dict]) -> None:
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
            self._add_file(
                f"{parent}/{display}",
                loader=lambda h=handle, r=ref: _text_bytes(
                    _source_doc_text(self.client.read_source_doc(h, r))
                ),
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
        """Materialize any connected source whose subtree contains `path`. No-op
        once a source has been expanded, and never triggered by listing the
        `sources/` directory itself — only by descending into a source."""
        for root in list(self._expanders):
            if path == root or path.startswith(f"{root}/"):
                self._expanders.pop(root)()

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


def _object_basename(name: str, object_id: str) -> str:
    return f"{_safe_name(name)}--{object_id[:8]}"


def _object_dir_name(name: str, object_id: str) -> str:
    return _object_basename(name, object_id)


def _object_file_name(name: str, object_id: str, default_extension: str) -> str:
    safe = _safe_name(name)
    stem, extension = posixpath.splitext(safe)
    if not extension:
        extension = default_extension
    return f"{stem or 'untitled'}--{object_id[:8]}{extension}"


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
