"""FUSE-backed virtual filesystem for browsing Stash from local tools."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import platform
import posixpath
import re
import stat
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .client import StashClient

BytesLoader = Callable[[], bytes]
BytesWriter = Callable[[bytes], None]


class StashMountError(Exception):
    pass


@dataclass
class VfsNode:
    path: str
    mode: int
    loader: BytesLoader | None = None
    writer: BytesWriter | None = None
    content: bytes | None = None
    size_hint: int | None = None
    children: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_dir(self) -> bool:
        return stat.S_ISDIR(self.mode)

    @property
    def is_file(self) -> bool:
        return stat.S_ISREG(self.mode)


@dataclass
class OpenFile:
    path: str
    buffer: bytearray
    writable: bool
    dirty: bool = False


class StashVfsModel:
    def __init__(self, client: StashClient, workspace_id: str | None = None):
        self.client = client
        self.workspace_id = workspace_id
        self.nodes: dict[str, VfsNode] = {}

    def refresh(self) -> None:
        self.nodes = {}
        self._add_dir("/")
        self._add_static_file(
            "/README.md",
            "\n".join(
                [
                    "# Stash",
                    "",
                    "This is a virtual filesystem view over Stash.",
                    "",
                    "- `workspaces/*/files` exposes folders, pages, and uploaded files.",
                    "- Markdown and HTML pages are writable; saves sync back to Stash.",
                    "- Uploaded files, sessions, stashes, and tables are read-only projections.",
                    "",
                ]
            ),
        )
        self._add_dir("/workspaces")

        workspaces = self.client.list_workspaces()
        if self.workspace_id:
            workspaces = [
                workspace for workspace in workspaces if str(workspace["id"]) == self.workspace_id
            ]
            if not workspaces:
                raise StashMountError(f"Workspace not found: {self.workspace_id}")

        for workspace in workspaces:
            self._add_workspace(workspace)

    def exists(self, path: str) -> bool:
        return self._clean_path(path) in self.nodes

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

    def write_file(self, path: str, content: bytes) -> None:
        node = self._get_node(path)
        if not node.is_file:
            raise IsADirectoryError(path)
        if node.writer is None:
            raise PermissionError(path)
        node.writer(content)
        node.content = bytes(content)
        node.size_hint = len(node.content)
        node.updated_at = time.time()

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
            "st_ctime": node.created_at,
            "st_mtime": node.updated_at,
            "st_atime": now,
        }

    def _add_workspace(self, workspace: dict) -> None:
        workspace_id = str(workspace["id"])
        workspace_name = _object_dir_name(workspace.get("name") or "workspace", workspace_id)
        workspace_path = f"/workspaces/{workspace_name}"
        overview = self.client.get_workspace_overview(workspace_id)

        self._add_dir(workspace_path)
        self._add_static_file(
            f"{workspace_path}/README.md",
            _json_header(
                {
                    "id": workspace_id,
                    "name": workspace.get("name", ""),
                    "description": workspace.get("description", ""),
                }
            ),
        )
        self._add_files_tree(workspace_path, workspace_id, overview.get("files", {}))
        self._add_stashes(workspace_path, overview.get("stashes", []))
        self._add_sessions(workspace_path, workspace_id, overview.get("sessions", []))
        self._add_tables(workspace_path, workspace_id)

    def _add_files_tree(self, workspace_path: str, workspace_id: str, tree: dict) -> None:
        root_path = f"{workspace_path}/files"
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
                loader=lambda ws=workspace_id, pid=page_id: self._load_page(ws, pid),
                writer=lambda body, ws=workspace_id, pid=page_id, ctype=content_type: self._write_page(
                    ws,
                    pid,
                    ctype,
                    body,
                ),
                writable=True,
            )

        for file in tree.get("files", []):
            file_id = str(file["id"])
            parent_path = (
                folder_path(str(file["folder_id"])) if file.get("folder_id") else root_path
            )
            name = _object_file_name(file.get("name") or "file", file_id, "")
            self._add_file(
                f"{parent_path}/{name}",
                loader=lambda ws=workspace_id, fid=file_id: self.client.download_ws_file(ws, fid),
                size_hint=file.get("size_bytes"),
            )

    def _add_stashes(self, workspace_path: str, stashes: list[dict]) -> None:
        stashes_path = f"{workspace_path}/stashes"
        self._add_dir(stashes_path)
        self._add_jsonl_file(f"{stashes_path}/_index.jsonl", stashes)
        for stash in stashes:
            stash_id = str(stash["id"])
            basename = _object_basename(stash.get("title") or "stash", stash_id)
            self._add_json_file(f"{stashes_path}/{basename}.json", stash)
            self._add_file(
                f"{stashes_path}/{basename}.md",
                loader=lambda slug=stash["slug"]: _text_bytes(self.client.get_stash_text(slug)),
            )

    def _add_sessions(self, workspace_path: str, workspace_id: str, sessions: list[dict]) -> None:
        sessions_path = f"{workspace_path}/sessions"
        self._add_dir(sessions_path)
        self._add_jsonl_file(f"{sessions_path}/_index.jsonl", sessions)
        for session in sessions:
            session_id = str(session["session_id"])
            row_id = str(session.get("id") or session_id)
            session_path = self._add_dir_child(
                sessions_path,
                _object_dir_name(session.get("title") or session_id, row_id),
            )
            self._add_json_file(f"{session_path}/metadata.json", session)
            self._add_file(
                f"{session_path}/events.json",
                loader=lambda ws=workspace_id, sid=session_id: _json_bytes(
                    {"events": self.client.get_transcript_events(ws, sid)}
                ),
            )
            self._add_file(
                f"{session_path}/transcript.jsonl",
                loader=lambda ws=workspace_id, sid=session_id: _text_bytes(
                    self.client.export_transcript_jsonl(ws, sid)
                ),
            )
            self._add_file(
                f"{session_path}/transcript.md",
                loader=lambda ws=workspace_id, sid=session_id: _text_bytes(
                    _session_markdown(self.client.get_transcript_events(ws, sid))
                ),
            )

    def _add_tables(self, workspace_path: str, workspace_id: str) -> None:
        tables_path = f"{workspace_path}/tables"
        self._add_dir(tables_path)
        tables = self.client.list_tables(workspace_id)
        self._add_jsonl_file(f"{tables_path}/_index.jsonl", tables)
        for table in tables:
            table_id = str(table["id"])
            table_path = self._add_dir_child(
                tables_path,
                _object_dir_name(table.get("name") or "table", table_id),
            )
            self._add_file(
                f"{table_path}/schema.json",
                loader=lambda ws=workspace_id, tid=table_id: _json_bytes(
                    self.client.get_table(ws, tid)
                ),
            )
            self._add_file(
                f"{table_path}/rows.json",
                loader=lambda ws=workspace_id, tid=table_id: _json_bytes(
                    self._load_all_table_rows(ws, tid)
                ),
            )
            self._add_file(
                f"{table_path}/rows.jsonl",
                loader=lambda ws=workspace_id, tid=table_id: _jsonl_bytes(
                    self._load_all_table_rows(ws, tid).get("rows", [])
                ),
            )

    def _load_page(self, workspace_id: str, page_id: str) -> bytes:
        page = self.client.get_page(workspace_id, page_id)
        if page.get("content_type") == "html":
            return _text_bytes(page.get("content_html") or "")
        return _text_bytes(page.get("content_markdown") or "")

    def _write_page(
        self, workspace_id: str, page_id: str, content_type: str, content: bytes
    ) -> None:
        text = content.decode("utf-8")
        if content_type == "html":
            self.client.update_page(workspace_id, page_id, content_type="html", content_html=text)
            return
        self.client.update_page(workspace_id, page_id, content=text)

    def _load_all_table_rows(self, workspace_id: str, table_id: str) -> dict:
        limit = 1000
        offset = 0
        rows: list[dict] = []
        total_count = 0
        while True:
            page = self.client.list_table_rows(workspace_id, table_id, limit=limit, offset=offset)
            page_rows = page.get("rows", [])
            rows.extend(page_rows)
            total_count = int(page.get("total_count", len(rows)))
            if not page.get("has_more"):
                break
            offset += limit
        return {"rows": rows, "total_count": total_count}

    def _add_dir(self, path: str) -> str:
        path = self._clean_path(path)
        if path in self.nodes:
            return path
        self.nodes[path] = VfsNode(path=path, mode=stat.S_IFDIR | 0o755)
        if path != "/":
            parent, name = self._split_parent(path)
            self.nodes[parent].children[name] = path
        return path

    def _add_dir_child(self, parent: str, name: str) -> str:
        name = self._unique_child_name(parent, name)
        return self._add_dir(f"{parent}/{name}")

    def _add_file(
        self,
        path: str,
        *,
        loader: BytesLoader | None = None,
        writer: BytesWriter | None = None,
        content: bytes | None = None,
        size_hint: int | None = None,
        writable: bool = False,
    ) -> str:
        path = self._clean_path(path)
        parent, requested_name = self._split_parent(path)
        name = self._unique_child_name(parent, requested_name)
        path = f"{parent}/{name}" if parent != "/" else f"/{name}"
        mode = stat.S_IFREG | (0o644 if writable else 0o444)
        self.nodes[path] = VfsNode(
            path=path,
            mode=mode,
            loader=loader,
            writer=writer,
            content=content,
            size_hint=(
                size_hint
                if size_hint is not None
                else (len(content) if content is not None else None)
            ),
        )
        self.nodes[parent].children[name] = path
        return path

    def _add_static_file(self, path: str, content: str) -> str:
        return self._add_file(path, content=_text_bytes(content))

    def _add_json_file(self, path: str, payload: dict) -> str:
        return self._add_file(path, content=_json_bytes(payload))

    def _add_jsonl_file(self, path: str, rows: list[dict]) -> str:
        return self._add_file(path, content=_jsonl_bytes(rows))

    def _get_node(self, path: str) -> VfsNode:
        path = self._clean_path(path)
        node = self.nodes.get(path)
        if node is None:
            raise FileNotFoundError(path)
        return node

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


class StashFuseOperations:
    def __init__(self, model: StashVfsModel):
        self.model = model
        self.handles: dict[int, OpenFile] = {}
        self.dir_handles: dict[int, str] = {}
        self.next_handle = 1
        self.lock = threading.Lock()

    def __call__(self, op: str, *args):
        handler = getattr(self, op, None)
        if handler is None:
            raise _fuse_error(errno.EFAULT)
        return handler(*args)

    def access(self, path: str, amode: int):
        if not self.model.exists(path):
            raise _fuse_error(errno.ENOENT)
        if amode & os.W_OK:
            node = self.model._get_node(path)
            if node.is_dir or node.writer is None:
                raise _fuse_error(errno.EROFS)
        return 0

    def getattr(self, path: str, fh=None):
        try:
            return self.model.getattr(path)
        except FileNotFoundError:
            raise _fuse_error(errno.ENOENT)

    def readdir(self, path: str, fh):
        try:
            path = self.model._clean_path(path)
            # fusepy does not expose the kernel readdir offset to this high-level operation.
            entries = [
                (".", self.model.getattr(path), 0),
                ("..", self.model.getattr(posixpath.dirname(path) or "/"), 0),
            ]
            for name in self.model.list_dir(path):
                child_path = posixpath.join(path, name)
                entries.append((name, self.model.getattr(child_path), 0))
            return entries
        except FileNotFoundError:
            raise _fuse_error(errno.ENOENT)
        except NotADirectoryError:
            raise _fuse_error(errno.ENOTDIR)

    def opendir(self, path: str):
        if not self.model.exists(path):
            raise _fuse_error(errno.ENOENT)
        node = self.model._get_node(path)
        if not node.is_dir:
            raise _fuse_error(errno.ENOTDIR)
        with self.lock:
            handle = self.next_handle
            self.next_handle += 1
            self.dir_handles[handle] = self.model._clean_path(path)
            return handle

    def releasedir(self, path: str, fh: int):
        self.dir_handles.pop(fh, None)
        return 0

    def open(self, path: str, flags: int):
        if not self.model.exists(path):
            raise _fuse_error(errno.ENOENT)
        writable = _flags_request_write(flags)
        node = self.model._get_node(path)
        if node.is_dir:
            raise _fuse_error(errno.EISDIR)
        if writable and node.writer is None:
            raise _fuse_error(errno.EROFS)
        data = b"" if flags & os.O_TRUNC else self.model.read_file(path)
        with self.lock:
            handle = self.next_handle
            self.next_handle += 1
            self.handles[handle] = OpenFile(path=path, buffer=bytearray(data), writable=writable)
            return handle

    def read(self, path: str, size: int, offset: int, fh: int):
        data = self.handles[fh].buffer if fh in self.handles else self.model.read_file(path)
        return bytes(data[offset : offset + size])

    def write(self, path: str, data: bytes, offset: int, fh: int):
        opened = self.handles.get(fh)
        if opened is None or not opened.writable:
            raise _fuse_error(errno.EBADF)
        end = offset + len(data)
        if end > len(opened.buffer):
            opened.buffer.extend(b"\x00" * (end - len(opened.buffer)))
        opened.buffer[offset:end] = data
        opened.dirty = True
        return len(data)

    def truncate(self, path: str, length: int, fh=None):
        if fh in self.handles:
            opened = self.handles[fh]
            if not opened.writable:
                raise _fuse_error(errno.EBADF)
            _resize_buffer(opened.buffer, length)
            opened.dirty = True
            return 0

        node = self.model._get_node(path)
        if node.writer is None:
            raise _fuse_error(errno.EROFS)
        data = bytearray(self.model.read_file(path))
        _resize_buffer(data, length)
        self.model.write_file(path, bytes(data))
        return 0

    def flush(self, path: str, fh: int):
        self._commit_handle(fh)
        return 0

    def fsync(self, path: str, fdatasync: bool, fh: int):
        self._commit_handle(fh)
        return 0

    def release(self, path: str, fh: int):
        self._commit_handle(fh)
        self.handles.pop(fh, None)
        return 0

    def utimens(self, path: str, times=None):
        if not self.model.exists(path):
            raise _fuse_error(errno.ENOENT)
        return 0

    def init(self, path: str):
        return None

    def destroy(self, path: str):
        return None

    def fsyncdir(self, path: str, fdatasync: bool, fh: int):
        return 0

    def statfs(self, path: str):
        return {
            "f_bsize": 4096,
            "f_frsize": 4096,
            "f_blocks": 1024 * 1024,
            "f_bavail": 1024 * 1024,
            "f_bfree": 1024 * 1024,
            "f_files": len(self.model.nodes) + 1024,
            "f_ffree": 1024 * 1024,
            "f_favail": 1024 * 1024,
        }

    def listxattr(self, path: str):
        return []

    def getxattr(self, path: str, name: str, position=0):
        raise _fuse_error(_enotsup())

    def setxattr(self, path: str, name: str, value: bytes, options: int, position=0):
        raise _fuse_error(_enotsup())

    def removexattr(self, path: str, name: str):
        raise _fuse_error(_enotsup())

    def readlink(self, path: str):
        raise _fuse_error(errno.ENOENT)

    def create(self, path: str, mode: int, fi=None):
        raise _fuse_error(errno.EROFS)

    def mknod(self, path: str, mode: int, dev: int):
        raise _fuse_error(errno.EROFS)

    def mkdir(self, path: str, mode: int):
        raise _fuse_error(errno.EROFS)

    def unlink(self, path: str):
        raise _fuse_error(errno.EROFS)

    def rmdir(self, path: str):
        raise _fuse_error(errno.EROFS)

    def rename(self, old: str, new: str):
        raise _fuse_error(errno.EROFS)

    def link(self, target: str, source: str):
        raise _fuse_error(errno.EROFS)

    def symlink(self, target: str, source: str):
        raise _fuse_error(errno.EROFS)

    def chmod(self, path: str, mode: int):
        raise _fuse_error(errno.EROFS)

    def chown(self, path: str, uid: int, gid: int):
        raise _fuse_error(errno.EROFS)

    def ioctl(self, path: str, cmd: int, arg, fip, flags: int, data):
        raise _fuse_error(errno.ENOTTY)

    def _commit_handle(self, fh: int) -> None:
        opened = self.handles.get(fh)
        if opened is None or not opened.dirty:
            return
        self.model.write_file(opened.path, bytes(opened.buffer))
        opened.dirty = False


def mount_stash(client: StashClient, mountpoint: Path, workspace_id: str | None = None) -> None:
    FUSE = _load_fuse_class()
    mountpoint.mkdir(parents=True, exist_ok=True)
    model = StashVfsModel(client, workspace_id=workspace_id)
    model.refresh()
    try:
        FUSE(
            StashFuseOperations(model),
            str(mountpoint),
            **_fuse_mount_options(mountpoint),
        )
    except (OSError, RuntimeError) as e:
        raise StashMountError(f"Stash mount failed: {e}") from e


def check_fuse_runtime() -> None:
    _load_fuse_class()
    _validate_fuse_provider()


def _load_fuse_class():
    _configure_fuse_library_path()
    try:
        from fuse import FUSE
    except (ImportError, OSError) as e:
        raise StashMountError(
            "Stash mount is experimental and requires a local FUSE runtime plus fusepy. "
            "Use `stash vfs` for the supported app-level virtual filesystem."
        ) from e
    return FUSE


def _configure_fuse_library_path() -> None:
    if os.environ.get("FUSE_LIBRARY_PATH") or sys.platform != "darwin":
        return

    macfuse_path = Path("/usr/local/lib/libfuse.2.dylib")
    if macfuse_path.is_file():
        os.environ["FUSE_LIBRARY_PATH"] = str(macfuse_path)


def _fuse_mount_options(mountpoint: Path) -> dict:
    options = {
        "foreground": True,
        "nothreads": True,
        "volname": "Stash",
    }
    if sys.platform != "darwin":
        return options

    _validate_fuse_provider()
    _require_macos_fskit_mountpoint(mountpoint)
    options["backend"] = "fskit"
    return options


def _validate_fuse_provider() -> None:
    if sys.platform != "darwin":
        return
    if _active_macos_fuse_provider() != "macfuse":
        raise StashMountError(
            "Stash mount is experimental on macOS and requires macFUSE 5 FSKit. "
            "Use `stash vfs` for the supported app-level virtual filesystem."
        )
    if not _macos_supports_fskit():
        raise StashMountError("Stash mount on macOS requires macOS 15.4 or later.")


def _active_macos_fuse_provider() -> str:
    path = os.environ.get("FUSE_LIBRARY_PATH", "")
    if "libfuse-t" in path:
        return "fuse-t"
    if Path("/usr/local/lib/libfuse.2.dylib").is_file():
        return "macfuse"
    return ""


def _macos_supports_fskit() -> bool:
    version = platform.mac_ver()[0]
    parts = version.split(".")
    if len(parts) < 2:
        return False
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except ValueError:
        return False
    return (major, minor) >= (15, 4)


def _require_macos_fskit_mountpoint(mountpoint: Path) -> None:
    absolute = mountpoint.expanduser().absolute()
    volumes = Path("/Volumes")
    if absolute == volumes or volumes in absolute.parents:
        return
    raise StashMountError(
        "Stash mount on macOS uses macFUSE FSKit, which requires a mount point under "
        "/Volumes. Re-run with: stash mount /Volumes/Stash"
    )


def _flags_request_write(flags: int) -> bool:
    return flags & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR) or bool(flags & os.O_TRUNC)


def _resize_buffer(buffer: bytearray, length: int) -> None:
    if length < len(buffer):
        del buffer[length:]
        return
    if length > len(buffer):
        buffer.extend(b"\x00" * (length - len(buffer)))


def _fuse_error(err: int) -> OSError:
    try:
        from fuse import FuseOSError

        return FuseOSError(err)
    except (ImportError, OSError):
        return OSError(err, os.strerror(err))


def _enotsup() -> int:
    return getattr(errno, "ENOTSUP", 45)


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


def _text_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _json_header(payload: dict) -> str:
    return f"```json\n{json.dumps(payload, indent=2, sort_keys=True, default=str)}\n```\n"


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
