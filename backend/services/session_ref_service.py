"""What session a handle names — the one place a title becomes an id.

A session has three identifiers: the agent's `session_id`, the `sessions` row
id, and a title. Only the title is ever shown to a person, and the VFS spells
that title its own way, so a handle arriving from `ls /sessions` or `stash
search` is a title in the VFS's spelling. Resolving lives here, server-side,
so the CLI, the MCP tools, and any HTTP caller all agree — and so it agrees
with the filesystem, whose names come from the same `session_dir_names`.

A handle that matches no title is already an id and is echoed back unchanged;
the endpoint that finally uses it rejects it if it is wrong. That keeps one
codepath in every caller: ask what this handle means, use the answer.
"""

from __future__ import annotations

from uuid import UUID

from stashvfs import safe_name, session_dir_names

from . import memory_service, session_service, session_title_service


class SessionRefAmbiguous(Exception):
    """One title, several sessions. The VFS already separates them with an id
    suffix, and those suffixed names resolve — so they are the way out."""

    def __init__(self, ref: str, names: list[str]):
        self.names = names
        listed = ", ".join(names)
        super().__init__(f"'{ref}' names {len(names)} sessions. Use one of: {listed}")


async def resolve(owner_user_id: UUID, user_id: UUID, ref: str) -> dict:
    """The session a live handle names."""
    sessions = await memory_service.list_scope_sessions(owner_user_id, user_id)
    return _match(ref, await _titled(owner_user_id, sessions))


async def resolve_trashed(owner_user_id: UUID, ref: str) -> dict:
    """The session a handle names in the trash, for `restore`. A trashed
    session is out of the scope listing, so it resolves against the same set
    `stash trash list` prints."""
    sessions = await session_service.list_trashed_sessions(owner_user_id)
    return _match(ref, await _titled(owner_user_id, sessions))


async def _titled(owner_user_id: UUID, sessions: list[dict]) -> list[dict]:
    # enqueue_missing=False: resolving a name is a read, and generating titles
    # for a whole scope on every `stash rm` would be a surprising cost.
    titles = await session_title_service.titles_for_sessions(
        owner_user_id, sessions, enqueue_missing=False
    )
    for session in sessions:
        session["title"] = titles[session["session_id"]]
    return sessions


def _match(ref: str, sessions: list[dict]) -> dict:
    """The session `ref` names, matched against every spelling it answers to:
    the stored title, the VFS's spelling of it, and the VFS directory name —
    which carries an id suffix when two sessions share a title.

    Raises on an ambiguous title rather than guessing: the callers are delete
    and publish.
    """
    handle = ref.strip()
    matches = [
        {**session, "name": name}
        for session, name in zip(sessions, session_dir_names(sessions))
        if session.get("title") and handle in (session["title"], safe_name(session["title"]), name)
    ]
    if not matches:
        return {
            "ref": ref,
            "matched": False,
            "session_id": ref,
            "id": ref,
            "title": None,
            "name": None,
        }
    if len({str(m["id"]) for m in matches}) > 1:
        raise SessionRefAmbiguous(ref, [m["name"] for m in matches])
    match = matches[0]
    return {
        "ref": ref,
        "matched": True,
        "session_id": str(match["session_id"]),
        "id": str(match["id"]),
        "title": match["title"],
        "name": match["name"],
    }
