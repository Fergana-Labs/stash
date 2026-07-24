"""The read contract a VFS backend must satisfy.

Two implementations exist: `cli.client.StashClient` (HTTP, for the `stash vfs`
command) and `backend.services.vfs_service.InProcessVfsClient` (nested ASGI, for
the `/api/v1/me/vfs` endpoint). `StashVfsModel` is written against this Protocol
and knows about neither.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol


class VfsClientError(Exception):
    """A VFS backend could not fetch a node.

    Raised per-node, not per-command: the shell catches this so that one
    unreadable document downgrades to a warning on stderr instead of failing the
    whole `grep -r`. `detail` is what gets printed.
    """

    def __init__(self, detail: object) -> None:
        self.detail = detail
        super().__init__(str(detail))


class VfsClient(Protocol):
    """Everything `StashVfsModel` reads. Listing calls run during `refresh()`;
    the rest are lazy loaders fired when a file's bytes are first read."""

    def internal_calls(self) -> AbstractContextManager[None]:
        """Requests issued inside this block are mount bookkeeping, not reads
        the user asked for. Implementations tag them `X-Stash-Via: auto` so
        content-activity analytics exclude them (see auth._set_request_via) —
        every VFS command rebuilds the tree, so counting these would log
        several listings per command, even for a `cat`."""
        ...

    def get_overview(self) -> dict: ...

    def get_memory_folder(self) -> dict: ...

    def get_page(self, page_id: str) -> dict: ...

    def download_file(self, file_id: str) -> bytes: ...

    def get_skill_text(self, slug: str) -> str: ...

    def get_transcript_events(self, session_id: str) -> list: ...

    def export_transcript_jsonl(self, session_id: str) -> str: ...

    def list_tables(self) -> list: ...

    def get_table(self, table_id: str) -> dict: ...

    def list_table_rows(self, table_id: str, limit: int = 50, offset: int = 0) -> dict: ...

    def list_sources(self) -> list: ...

    def list_source_entries_page(
        self, source: str, path: str = "", after: str = ""
    ) -> tuple[list, bool]: ...

    def read_source_doc(self, source: str, ref: str) -> dict: ...


class MachineVfsClient(VfsClient, Protocol):
    """A `VfsClient` that can also read the user's cloud computer. Only the CLI
    implements this; it is what `include_computer=True` requires."""

    def machine_fs_list(self, path: str) -> list: ...

    def machine_fs_read(self, path: str) -> bytes: ...
