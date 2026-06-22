"""Data-level test for the workspace-collapse migration (0118 -> 0120).

0118 is the access-preservation heart of the workspace expunge: it turns every
non-creator `workspace_members` row into explicit `shares`, re-homes content
onto the creator's single scope, and drops the multi-tenancy tables. The
chain is ONE-WAY (`downgrade` raises), so a regression that dropped a member's
access or mapped the wrong permission tier could never be rolled back.

The other migration tests only run `alembic upgrade head` on an empty DB and
assert it doesn't error — that can't catch a data-mapping bug. This test seeds a
realistic pre-0118 world on an isolated database, runs the chain, and asserts
the resulting `shares` + `owner_user_id` grant exactly the access the
memberships did (viewer -> read, editor -> write, creator owns, stranger gets
nothing, nested content rides the folder-share cascade).
"""

import asyncio
import os
import subprocess
import sys
import uuid

import asyncpg

_BASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://stash:stash@localhost:5432/stash_test",
)
_ADMIN_URL = _BASE_URL.rsplit("/", 1)[0] + "/postgres"
_MIG_DB = "stash_mig_members_" + uuid.uuid4().hex[:12]
_MIG_URL = _BASE_URL.rsplit("/", 1)[0] + "/" + _MIG_DB


def _alembic(target: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = _MIG_URL
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic upgrade {target} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


async def _create_db() -> None:
    conn = await asyncpg.connect(_ADMIN_URL)
    await conn.execute(f'DROP DATABASE IF EXISTS "{_MIG_DB}"')
    await conn.execute(f'CREATE DATABASE "{_MIG_DB}"')
    await conn.close()
    conn = await asyncpg.connect(_MIG_URL)
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await conn.close()


async def _drop_db() -> None:
    conn = await asyncpg.connect(_ADMIN_URL)
    await conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = $1 AND pid <> pg_backend_pid()",
        _MIG_DB,
    )
    await conn.execute(f'DROP DATABASE IF EXISTS "{_MIG_DB}"')
    await conn.close()


async def _user(conn, label: str) -> uuid.UUID:
    return await conn.fetchval(
        "INSERT INTO users (name, display_name) VALUES ($1, $1) RETURNING id", label
    )


async def _workspace(conn, creator: uuid.UUID) -> uuid.UUID:
    return await conn.fetchval(
        "INSERT INTO workspaces (name, creator_id, invite_code) VALUES ('ws', $1, $2) RETURNING id",
        creator,
        uuid.uuid4().hex[:12],
    )


async def _member(conn, ws: uuid.UUID, user: uuid.UUID, role: str, primary: bool) -> None:
    await conn.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role, is_primary) "
        "VALUES ($1, $2, $3, $4)",
        ws,
        user,
        role,
        primary,
    )


def test_members_become_shares_preserving_access():
    """Seed pre-0118, run 0118->0120, assert access is preserved exactly."""
    asyncio.run(_run())


async def _run():
    await _create_db()
    try:
        _alembic("0117")

        conn = await asyncpg.connect(_MIG_URL)
        try:
            creator = await _user(conn, "creator")
            viewer = await _user(conn, "viewer")
            editor = await _user(conn, "editor")
            stranger = await _user(conn, "stranger")

            # The creator's primary workspace, shared with a viewer and an editor.
            ws = await _workspace(conn, creator)
            await _member(conn, ws, creator, "owner", True)
            await _member(conn, ws, viewer, "viewer", False)
            await _member(conn, ws, editor, "editor", False)

            # Everyone else's primary workspace (auto-provisioned at signup).
            for u in (viewer, editor, stranger):
                wu = await _workspace(conn, u)
                await _member(conn, wu, u, "owner", True)

            # A second, non-primary workspace of the creator — exercises re-home.
            ws2 = await _workspace(conn, creator)
            await _member(conn, ws2, creator, "owner", False)

            root_folder = await conn.fetchval(
                "INSERT INTO folders (name, created_by, workspace_id) VALUES ('rf', $1, $2) "
                "RETURNING id",
                creator,
                ws,
            )
            root_page = await conn.fetchval(
                "INSERT INTO pages (name, created_by, workspace_id, folder_id) "
                "VALUES ('rp', $1, $2, NULL) RETURNING id",
                creator,
                ws,
            )
            nested_page = await conn.fetchval(
                "INSERT INTO pages (name, created_by, workspace_id, folder_id) "
                "VALUES ('np', $1, $2, $3) RETURNING id",
                creator,
                ws,
                root_folder,
            )
            rehomed_page = await conn.fetchval(
                "INSERT INTO pages (name, created_by, workspace_id, folder_id) "
                "VALUES ('p2', $1, $2, NULL) RETURNING id",
                creator,
                ws2,
            )
        finally:
            await conn.close()

        _alembic("0120")

        conn = await asyncpg.connect(_MIG_URL)
        try:
            # The multi-tenancy tables are gone.
            for dead in ("workspaces", "workspace_members"):
                exists = await conn.fetchval(
                    "SELECT to_regclass($1)", f"public.{dead}"
                )
                assert exists is None, f"{dead} should be dropped"

            # All content (including the re-homed page) now belongs to the creator.
            for obj in (root_folder, root_page, nested_page):
                owner = await conn.fetchval(
                    "SELECT owner_user_id FROM pages WHERE id = $1", obj
                ) or await conn.fetchval("SELECT owner_user_id FROM folders WHERE id = $1", obj)
                assert owner == creator
            assert (
                await conn.fetchval("SELECT owner_user_id FROM pages WHERE id = $1", rehomed_page)
                == creator
            ), "non-primary workspace content must re-home onto the creator's scope"

            async def grant(object_type, object_id, principal):
                return await conn.fetchval(
                    "SELECT permission FROM shares WHERE object_type = $1 AND object_id = $2 "
                    "AND principal_type = 'user' AND principal_id = $3",
                    object_type,
                    object_id,
                    principal,
                )

            # Viewer -> read, editor -> write, on the root objects.
            assert await grant("folder", root_folder, viewer) == "read"
            assert await grant("page", root_page, viewer) == "read"
            assert await grant("folder", root_folder, editor) == "write"
            assert await grant("page", root_page, editor) == "write"

            # The creator is the owner, never a share principal of their own content.
            assert await grant("folder", root_folder, creator) is None
            assert await grant("page", root_page, creator) is None

            # Nested content is covered by the root-folder share cascade, not a
            # direct share — the migration only shares root objects.
            assert await grant("page", nested_page, viewer) is None

            # The stranger was never a member and gets nothing.
            stranger_shares = await conn.fetchval(
                "SELECT count(*) FROM shares WHERE principal_id = $1", stranger
            )
            assert stranger_shares == 0

            # The converted shares carry the creator's scope as owner.
            share_owner = await conn.fetchval(
                "SELECT DISTINCT owner_user_id FROM shares WHERE principal_id = $1", viewer
            )
            assert share_owner == creator
        finally:
            await conn.close()
    finally:
        await _drop_db()
