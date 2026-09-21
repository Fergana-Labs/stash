from uuid import uuid4

import numpy as np
import pytest

from backend.services import embeddings
from backend.tasks.embeddings import _ensure_embedding_space


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", ["same", "different", None])
async def test_model_check_never_deletes_existing_vectors(pool, monkeypatch, stored):
    monkeypatch.setattr(embeddings, "space_id", lambda: "same")
    await pool.execute("DELETE FROM embedding_space_state")
    if stored is not None:
        await pool.execute("INSERT INTO embedding_space_state (space_id) VALUES ($1)", stored)
    uid = uuid4()
    await pool.execute("INSERT INTO users (id,name,display_name) VALUES ($1,$2,$2)", uid, uid.hex)
    vector = np.ones(384, dtype=np.float32)
    page = await pool.fetchval(
        "INSERT INTO pages (owner_user_id,created_by,name,embedding,embed_stale) "
        "VALUES ($1,$1,'Keep my search vector',$2,FALSE) RETURNING id",
        uid,
        vector,
    )
    if stored == "same":
        await _ensure_embedding_space()
    else:
        with pytest.raises(RuntimeError, match="Embedding space mismatch"):
            await _ensure_embedding_space()
    row = await pool.fetchrow("SELECT embedding,embed_stale FROM pages WHERE id=$1", page)
    np.testing.assert_array_equal(row["embedding"], vector)
    assert row["embed_stale"] is False
    assert await pool.fetchval("SELECT space_id FROM embedding_space_state") == stored
