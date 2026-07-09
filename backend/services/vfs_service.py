"""Server-side execution of the Stash VFS shell.

`stash vfs "ls /"` builds the filesystem in the CLI process out of ordinary REST
reads. Agents that have no shell to install a CLI into — a Vercel function, an
MCP client — need the same thing over HTTP, so this module runs the identical
`StashVfsModel` + `SkillAppVfsShell` inside the API.

The model reads through `InProcessVfsClient`, which re-enters this FastAPI app
over ASGI rather than calling services directly. That costs a routing hop per
read and buys the thing that matters: every route's authorization runs exactly as
it does for any other caller, so there is one implementation of who-can-read-what
instead of two that drift.
"""

from __future__ import annotations

import asyncio
import functools
import threading

import anyio
import anyio.to_thread
import httpx

from stashvfs import SkillAppVfsShell, StashVfsModel, VfsClientError

# A `grep -r /` loads every document it walks, one nested request each. Past this
# many the caller has asked for a scan, not a search — fail loud rather than sit
# on an open connection until the client's own timeout fires.
MAX_DOCUMENT_READS = 400

SOURCE_ENTRIES_PAGE = 1000


class VfsBudgetExceeded(Exception):
    """More document reads than one shell invocation is allowed. Deliberately not
    a VfsClientError: the shell downgrades those to per-file warnings, and this
    must abort the whole command."""


class InProcessVfsClient:
    """`VfsClient` served by the running app over nested ASGI calls.

    Every method mirrors the `cli.client.StashClient` method of the same name,
    down to the query parameters — the two are alternate transports for one API.
    """

    def __init__(self, http: httpx.AsyncClient, loop: asyncio.AbstractEventLoop) -> None:
        self._http = http
        self._loop = loop
        self._document_reads = 0
        self._reads_lock = threading.Lock()

    def _request(self, method: str, endpoint: str, **params) -> httpx.Response:
        # Dispatched onto the app's event loop from whichever thread we are on.
        # `StashVfsModel.prefetch` calls loaders from a pool, so this must work
        # from an arbitrary thread — not just anyio's worker, which is all
        # `anyio.from_thread.run` supports.
        future = asyncio.run_coroutine_threadsafe(
            self._http.request(method, endpoint, params=params or None), self._loop
        )
        response = future.result()
        if response.status_code >= 400:
            raise VfsClientError(_error_detail(response))
        return response

    def _get(self, endpoint: str, **params) -> dict | list:
        return self._request("GET", endpoint, **params).json()

    def _read_document(self, method: str, endpoint: str, **params) -> httpx.Response:
        """A fetch of a node's bytes, as opposed to a listing. Only these are
        budgeted: listings are bounded by the model's own entry ceiling."""
        with self._reads_lock:
            self._document_reads += 1
            over_budget = self._document_reads > MAX_DOCUMENT_READS
        if over_budget:
            raise VfsBudgetExceeded(
                f"command read more than {MAX_DOCUMENT_READS} documents; "
                "scope it to a subdirectory or use search"
            )
        return self._request(method, endpoint, **params)

    # ── Listings, walked during refresh() ──────────────────────────────

    def get_overview(self) -> dict:
        return self._get("/api/v1/me/overview")

    def get_memory_folder(self) -> dict:
        return self._get("/api/v1/me/memory-folder")

    def list_tables(self) -> list:
        return self._get("/api/v1/me/tables")["tables"]

    def list_sources(self) -> list:
        return self._get("/api/v1/me/sources")["sources"]

    def list_source_entries_page(
        self, source: str, path: str = "", after: str = ""
    ) -> tuple[list, bool]:
        data = self._get(
            f"/api/v1/me/sources/{source}/entries",
            path=path,
            limit=SOURCE_ENTRIES_PAGE + 1,
            after=after,
        )
        entries = data["entries"]
        truncated = len(entries) > SOURCE_ENTRIES_PAGE
        return entries[:SOURCE_ENTRIES_PAGE], truncated

    # ── Node bodies, loaded lazily on read ─────────────────────────────

    def get_page(self, page_id: str) -> dict:
        return self._read_document("GET", f"/api/v1/pages/{page_id}").json()

    def download_file(self, file_id: str) -> bytes:
        return self._read_document("GET", f"/api/v1/me/files/{file_id}/download").content

    def get_skill_text(self, slug: str) -> str:
        return self._read_document("GET", f"/api/v1/skills/{slug}", format="text").text

    def get_transcript_events(self, session_id: str) -> list:
        path = f"/api/v1/me/transcripts/{session_id}/events"
        return self._read_document("GET", path).json()["events"]

    def export_transcript_jsonl(self, session_id: str) -> str:
        path = f"/api/v1/me/transcripts/{session_id}/export.jsonl"
        return self._read_document("GET", path).text

    def get_table(self, table_id: str) -> dict:
        return self._read_document("GET", f"/api/v1/me/tables/{table_id}").json()

    def list_table_rows(self, table_id: str, limit: int = 50, offset: int = 0) -> dict:
        path = f"/api/v1/me/tables/{table_id}/rows"
        return self._read_document("GET", path, limit=limit, offset=offset, sort_order="asc").json()

    def read_source_doc(self, source: str, ref: str) -> dict:
        return self._read_document("GET", f"/api/v1/me/sources/{source}/doc", ref=ref).json()


def _error_detail(response: httpx.Response) -> str:
    """The route's `detail` when it raised HTTPException, else the status line.
    This lands in the shell's stderr, so a 404 on one document reads as a warning
    naming that document."""
    if response.headers.get("content-type", "").startswith("application/json"):
        body = response.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
    return f"HTTP {response.status_code}"


def _run_script(
    http: httpx.AsyncClient, loop: asyncio.AbstractEventLoop, script: str, cwd: str
) -> dict:
    """Blocking: the model and shell are synchronous, and their lazy loaders reach
    back into `loop` to issue their requests. Runs in a worker thread for that
    reason — see `run_vfs_script`."""
    model = StashVfsModel(InProcessVfsClient(http, loop), include_computer=False)
    model.refresh()
    result = SkillAppVfsShell(model, cwd=cwd).run(script)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "cwd": result.cwd,
    }


async def run_vfs_script(app, authorization: str, script: str, cwd: str) -> dict:
    """Execute one read-only shell script against the caller's Stash.

    `authorization` is forwarded verbatim onto every nested request, so the VFS
    sees precisely what that credential sees anywhere else in the API.
    """
    loop = asyncio.get_running_loop()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://vfs.internal",
        headers={"Authorization": authorization},
        timeout=None,
    ) as http:
        return await anyio.to_thread.run_sync(
            functools.partial(_run_script, http, loop, script, cwd)
        )
