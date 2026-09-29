"""Annotations on traces: a + or − rating, a comment, or both, on a trace or one step."""

from uuid import UUID

from ...database import get_pool

ANNOTATION_SELECT = """
    SELECT a.*, u.name AS author_name
    FROM rm_annotations a
    JOIN users u ON u.id = a.owner_user_id
"""


class AnnotationInvalid(ValueError):
    pass


def _annotation(row) -> dict:
    return {
        "id": row["id"],
        "trace_id": row["trace_id"],
        "step_id": row["step_id"],
        "rating": row["rating"],
        "comment": row["comment"],
        "quote": row["quote"],
        "label_error": row["label_error"],
        "label_error_note": row["label_error_note"],
        "author_id": row["owner_user_id"],
        "author_name": row["author_name"],
        "created_at": row["created_at"],
    }


def _check_rating_or_comment(rating: int | None, comment: str | None) -> None:
    if rating is None and not comment:
        raise AnnotationInvalid("an annotation needs a rating, a comment, or both")


def _check_ratable(step_role: str) -> None:
    # The reward model never sees system steps, so a rating on one could not train.
    if step_role == "system":
        raise AnnotationInvalid("system steps can be commented on but not rated")


async def _get(owner_user_id: UUID, annotation_id: UUID) -> dict | None:
    row = await get_pool().fetchrow(
        ANNOTATION_SELECT + " WHERE a.owner_user_id = $1 AND a.id = $2",
        owner_user_id,
        annotation_id,
    )
    return _annotation(row) if row else None


async def list_for_trace(trace_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        ANNOTATION_SELECT + " WHERE a.trace_id = $1 ORDER BY a.created_at, a.id", trace_id
    )
    return [_annotation(row) for row in rows]


async def create(
    owner_user_id: UUID,
    trace_id: UUID,
    step_id: UUID | None,
    rating: int | None,
    comment: str | None,
    quote: dict | None,
) -> dict | None:
    """Returns None when the trace doesn't exist for this owner."""
    pool = get_pool()
    owns_trace = await pool.fetchval(
        "SELECT 1 FROM rm_traces WHERE owner_user_id = $1 AND id = $2", owner_user_id, trace_id
    )
    if not owns_trace:
        return None
    _check_rating_or_comment(rating, comment)

    if step_id is not None:
        step = await pool.fetchrow(
            "SELECT role, content FROM rm_trace_steps WHERE trace_id = $1 AND id = $2",
            trace_id,
            step_id,
        )
        if step is None:
            raise AnnotationInvalid("step_id is not a step of this trace")
        if rating is not None:
            _check_ratable(step["role"])
        if quote is not None and quote["text"] not in step["content"]:
            raise AnnotationInvalid("quote text does not appear in the step's content")
    elif quote is not None:
        raise AnnotationInvalid("a quote needs a step_id")

    annotation_id = await pool.fetchval(
        """
        INSERT INTO rm_annotations (owner_user_id, trace_id, step_id, rating, comment, quote)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        owner_user_id,
        trace_id,
        step_id,
        rating,
        comment,
        quote,
    )
    return await _get(owner_user_id, annotation_id)


async def update(owner_user_id: UUID, annotation_id: UUID, changes: dict) -> dict | None:
    """Apply only the fields the caller sent. Returns None when not found."""
    current = await _get(owner_user_id, annotation_id)
    if current is None:
        return None
    merged = {**current, **changes}
    _check_rating_or_comment(merged["rating"], merged["comment"])
    if merged["rating"] is not None and merged["step_id"] is not None:
        role = await get_pool().fetchval(
            "SELECT role FROM rm_trace_steps WHERE id = $1", merged["step_id"]
        )
        _check_ratable(role)

    await get_pool().execute(
        """
        UPDATE rm_annotations
        SET rating = $3, comment = $4, label_error = $5, label_error_note = $6, updated_at = now()
        WHERE owner_user_id = $1 AND id = $2
        """,
        owner_user_id,
        annotation_id,
        merged["rating"],
        merged["comment"],
        merged["label_error"],
        merged["label_error_note"],
    )
    return await _get(owner_user_id, annotation_id)


async def delete(owner_user_id: UUID, annotation_id: UUID) -> bool:
    result = await get_pool().execute(
        "DELETE FROM rm_annotations WHERE owner_user_id = $1 AND id = $2",
        owner_user_id,
        annotation_id,
    )
    return result == "DELETE 1"


async def export_annotations(owner_user_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        """
        SELECT a.trace_id, t.external_id AS trace_external_id, s.idx AS step_index,
               a.rating, a.comment, a.quote, a.label_error, a.label_error_note,
               u.name AS author, a.created_at
        FROM rm_annotations a
        JOIN rm_traces t ON t.id = a.trace_id
        JOIN users u ON u.id = a.owner_user_id
        LEFT JOIN rm_trace_steps s ON s.id = a.step_id
        WHERE a.owner_user_id = $1
        ORDER BY a.created_at, a.id
        """,
        owner_user_id,
    )
    return [
        {
            "trace_id": str(row["trace_id"]),
            "trace_external_id": row["trace_external_id"],
            "step_index": row["step_index"],
            "rating": row["rating"],
            "comment": row["comment"],
            "quote": row["quote"],
            "label_error": row["label_error"],
            "label_error_note": row["label_error_note"],
            "author": row["author"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
