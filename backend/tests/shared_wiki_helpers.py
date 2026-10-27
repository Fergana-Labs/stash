"""Explicitly approve test fixtures; production code must use privacy.review first."""

from uuid import UUID

from backend.services import shared_wiki_privacy as privacy


async def approve_fixture_pages(conn, workspace):
    rows = await conn.fetch(
        "WITH RECURSIVE tree AS (SELECT id FROM folders WHERE id=$1 "
        "UNION ALL SELECT f.id FROM folders f JOIN tree t ON f.parent_folder_id=t.id) "
        "SELECT p.* FROM pages p JOIN tree t ON p.folder_id=t.id",
        UUID(str(workspace["external_wiki_folder_id"])),
    )
    for row in rows:
        await privacy.record_approval(conn, UUID(str(workspace["id"])), dict(row))
