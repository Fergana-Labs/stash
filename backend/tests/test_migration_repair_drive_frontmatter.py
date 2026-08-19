"""Data-level test for 0187, the Google-export frontmatter backfill.

0187 rewrites stored `drive_documents.content`, and a backfill that rewrites
user content is exactly where a wrong guard silently corrupts a document
someone else authored. The chain-runs-clean tests can't catch that; this seeds
a pre-0187 world on an isolated database, runs the migration, and asserts each
kind of row gets exactly the treatment it should: exporter damage repaired,
prose and hand-authored files byte-identical.
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
_MIG_DB = "stash_mig_frontmatter_" + uuid.uuid4().hex[:12]
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


# The four kinds of stored row the backfill must treat differently.

DAMAGED_DOC_EXPORT = (
    "\\---  \n**name:** “Brake Shoes”  \n"
    'description: "Use when a part\\_number is given."  \n\\---  \n\nCheck the drum.\n'
)

CURLY_ONLY_DOC_EXPORT = (
    "---\nname: “Brake Shoes”\ndescription: “Use when brakes squeal.”\n---\n\nCheck the drum.\n"
)

ORDINARY_PROSE = (
    "---\n\nStandup 9:00 AM  \nAttendees: **Ann**, Bob  \n"
    "Notes at https://wiki.example.com/turbo  \n\n---\n\nAction items below.\n"
)

HAND_AUTHORED_SKILL_MD = (
    '---\nname: "Fitment"\ndescription: "Use for *fitment* checks."\n---\n\nMeasure twice.\n'
)


async def _seed() -> dict[str, uuid.UUID]:
    conn = await asyncpg.connect(_MIG_URL)
    user_id = await conn.fetchval(
        "INSERT INTO users (name, display_name) VALUES ('mig-frontmatter-user', 'u') RETURNING id",
    )
    source_id = await conn.fetchval(
        "INSERT INTO user_sources (owner_user_id, source_type, external_ref, display_name, "
        "binds_skills) VALUES ($1, 'google_drive_folder', 'folder-1', 'Shelf', TRUE) "
        "RETURNING id",
        user_id,
    )
    ids: dict[str, uuid.UUID] = {}
    for path, content in [
        ("damaged.gdoc", DAMAGED_DOC_EXPORT),
        ("curly.gdoc", CURLY_ONLY_DOC_EXPORT),
        ("notes.gdoc", ORDINARY_PROSE),
        ("SKILL.md", HAND_AUTHORED_SKILL_MD),
    ]:
        ids[path] = await conn.fetchval(
            "INSERT INTO drive_documents (owner_user_id, source_id, path, name, external_ref, "
            "content, content_hash, extraction_status) "
            "VALUES ($1, $2, $3, $3, $3, $4, md5($4), 'done') RETURNING id",
            user_id,
            source_id,
            path,
            content,
        )
    await conn.close()
    return ids


async def _fetch(ids: dict[str, uuid.UUID]) -> dict[str, asyncpg.Record]:
    conn = await asyncpg.connect(_MIG_URL)
    rows = {
        path: await conn.fetchrow(
            "SELECT content, content_hash, embed_stale FROM drive_documents WHERE id = $1",
            row_id,
        )
        for path, row_id in ids.items()
    }
    await conn.close()
    return rows


def test_backfill_repairs_exporter_damage_and_nothing_else():
    asyncio.run(_create_db())
    try:
        _alembic("0186")
        ids = asyncio.run(_seed())
        _alembic("head")
        rows = asyncio.run(_fetch(ids))

        damaged = rows["damaged.gdoc"]
        assert damaged["content"] == (
            '---\nname: "Brake Shoes"\n'
            'description: "Use when a part_number is given."\n---\n\nCheck the drum.\n'
        )
        assert damaged["embed_stale"] is True

        curly = rows["curly.gdoc"]
        assert curly["content"] == (
            '---\nname: "Brake Shoes"\ndescription: "Use when brakes squeal."\n'
            "---\n\nCheck the drum.\n"
        )
        assert curly["embed_stale"] is True

        # The prose row and the hand-authored SKILL.md are someone's own text:
        # byte-identical or the backfill has corrupted a document.
        assert rows["notes.gdoc"]["content"] == ORDINARY_PROSE
        assert rows["notes.gdoc"]["embed_stale"] is False
        assert rows["SKILL.md"]["content"] == HAND_AUTHORED_SKILL_MD
        assert rows["SKILL.md"]["embed_stale"] is False
    finally:
        asyncio.run(_drop_db())
