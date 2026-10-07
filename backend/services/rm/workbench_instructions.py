"""Release reviewed instructions and verify their presence in captured context.

An offer is not a load receipt. The only transition to `captured` requires the
exact released bytes and delivery marker in a model-visible context step of
the same owner's native session. Neither skill synchronization, hook execution,
nor an assistant's claim that it followed a skill is sufficient evidence.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from ...database import get_pool

# Wire limits/format match stashai.plugin.workbench. Keep the backend image
# independent of the CLI package; native-capture tests exercise both renderers.
MAX_INSTRUCTION_CHARS = 16000
MAX_CONTEXT_CHARS = 64000


class InstructionInvalid(ValueError):
    pass


def _repository(value: str) -> str:
    return value.rstrip("/") or "/"


def _scope_matches(scope: dict, source_format: str, repository: str) -> bool:
    return (not scope.get("source_format") or scope["source_format"] == source_format) and (
        not scope.get("repository") or _repository(scope["repository"]) == repository
    )


def _snapshot(content: dict) -> tuple[str, str]:
    text = content.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_INSTRUCTION_CHARS:
        raise InstructionInvalid(
            f"Instruction text must contain 1–{MAX_INSTRUCTION_CHARS} characters"
        )
    return text, hashlib.sha256(text.encode()).hexdigest()


def instruction_context(delivery: dict) -> str:
    text, digest = _snapshot({"text": delivery["content"]})
    if digest != delivery["content_sha256"]:
        raise InstructionInvalid("Released instruction content hash does not match")
    return (
        f'<stash-workbench-instruction delivery="{delivery["id"]}" '
        f'version="{delivery["change_id"]}" sha256="{digest}">\n'
        f"{text}\n</stash-workbench-instruction>"
    )


async def _head(conn, grader_id: UUID):
    return await conn.fetchrow(
        "SELECT r.* FROM rm_wb_instruction_heads h "
        "JOIN rm_wb_instruction_releases r ON r.id=h.release_id WHERE h.grader_id=$1",
        grader_id,
    )


async def get_head(owner: UUID, grader_id: UUID) -> UUID | None:
    return await get_pool().fetchval(
        "SELECT r.change_id FROM rm_wb_instruction_heads h "
        "JOIN rm_wb_instruction_releases r ON r.id=h.release_id "
        "WHERE r.owner_user_id=$1 AND h.grader_id=$2",
        owner,
        grader_id,
    )


async def _append_release(conn, owner, grader_id, change_id, action, scope, text, digest):
    previous = await _head(conn, grader_id)
    row = await conn.fetchrow(
        "INSERT INTO rm_wb_instruction_releases "
        "(owner_user_id,grader_id,change_id,previous_change_id,action,scope,content,content_sha256) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *",
        owner,
        grader_id,
        change_id,
        previous["change_id"] if previous else None,
        action,
        scope,
        text,
        digest,
    )
    await conn.execute(
        "INSERT INTO rm_wb_instruction_heads (grader_id,release_id) VALUES ($1,$2) "
        "ON CONFLICT (grader_id) DO UPDATE SET release_id=EXCLUDED.release_id",
        grader_id,
        row["id"],
    )
    return dict(row)


async def release_instruction(owner: UUID, change_id: UUID) -> dict:
    async with get_pool().acquire() as conn, conn.transaction():
        from .workbench import mutation_lock

        await mutation_lock(conn, owner)
        # Lock the grader first for the same ordering as rollback/release peers.
        grader = await conn.fetchrow(
            "SELECT g.* FROM rm_wb_graders g JOIN rm_wb_changes c ON c.grader_id=g.id "
            "WHERE c.id=$1 AND c.owner_user_id=$2 AND g.owner_user_id=$2 FOR UPDATE OF g",
            change_id,
            owner,
        )
        if not grader:
            raise InstructionInvalid("Instruction change not found")
        feedback_id = await conn.fetchval(
            "SELECT feedback_id FROM rm_wb_changes WHERE id=$1", change_id
        )
        # Review locks feedback before updating its changes. Match that order
        # so an instruction release cannot deadlock with a concurrent review.
        feedback = (
            await conn.fetchrow(
                "SELECT * FROM rm_wb_feedback WHERE id=$1 AND owner_user_id=$2 FOR SHARE",
                feedback_id,
                owner,
            )
            if feedback_id
            else None
        )
        change = await conn.fetchrow(
            "SELECT * FROM rm_wb_changes WHERE id=$1 FOR UPDATE", change_id
        )
        if change["feedback_id"] != feedback_id:
            raise InstructionInvalid("Source feedback changed; review the instruction again")
        if change["kind"] != "instruction":
            raise InstructionInvalid("This change is not an instruction")
        current = await _head(conn, grader["id"])
        if change["status"] == "released" and current and current["change_id"] == change_id:
            return dict(current)
        if change["status"] != "checked":
            raise InstructionInvalid("Only a checked instruction draft can be released")
        if (change["check_report"] or {}).get("passed") is not True:
            raise InstructionInvalid("Instruction checks must pass before release")
        if feedback_id is not None and (not feedback or feedback["review_status"] != "accepted"):
            raise InstructionInvalid("Accept the source feedback before releasing instructions")
        if change["parent_version_id"] != (current["change_id"] if current else None):
            raise InstructionInvalid(
                "Active instructions changed; review a draft against the current version"
            )
        text, digest = _snapshot(change["content"])
        result = await _append_release(
            conn, owner, grader["id"], change_id, "release", grader["scope"], text, digest
        )
        await conn.execute(
            "UPDATE rm_wb_changes SET status='released',released_at=now(),updated_at=now() WHERE id=$1",
            change_id,
        )
        return result


async def rollback(owner: UUID, grader_id: UUID, change_id: UUID | None) -> dict:
    """Restore a prior snapshot for future sessions; None disables delivery."""
    async with get_pool().acquire() as conn, conn.transaction():
        grader = await conn.fetchrow(
            "SELECT * FROM rm_wb_graders WHERE id=$1 AND owner_user_id=$2 FOR UPDATE",
            grader_id,
            owner,
        )
        if not grader:
            raise InstructionInvalid("Grader not found")
        if change_id is None:
            return await _append_release(
                conn, owner, grader_id, None, "disable", grader["scope"], None, None
            )
        previous = await conn.fetchrow(
            "SELECT * FROM rm_wb_instruction_releases "
            "WHERE owner_user_id=$1 AND grader_id=$2 AND change_id=$3 "
            "ORDER BY created_at,id LIMIT 1",
            owner,
            grader_id,
            change_id,
        )
        if not previous:
            raise InstructionInvalid(
                "Rollback requires a previously released instruction in this scope"
            )
        return await _append_release(
            conn,
            owner,
            grader_id,
            change_id,
            "rollback",
            previous["scope"],
            previous["content"],
            previous["content_sha256"],
        )


async def deliver(owner: UUID, session_id: str, source_format: str, repository: str) -> dict:
    """Offer exact released versions once per session/scope, never a saved draft.

    Resumes keep the original assignment. A release/rollback cannot replace a
    version already offered to a running session, even when no receipt exists.
    """
    if source_format not in {"codex", "claude_code"}:
        raise InstructionInvalid("Instruction context delivery supports Codex and Claude Code")
    if not session_id or not repository:
        raise InstructionInvalid("Session id and repository are required")
    repository = _repository(repository)
    async with get_pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1))", f"wb_instruction:{owner}:{session_id}"
        )
        session = await conn.fetchrow(
            "SELECT cwd,started_at FROM sessions "
            "WHERE owner_user_id=$1 AND session_id=$2 AND deleted_at IS NULL",
            owner,
            session_id,
        )
        if not session or _repository(session["cwd"] or "") != repository:
            raise InstructionInvalid("Recorded session and repository do not match")
        existing = await conn.fetch(
            "SELECT * FROM rm_wb_instruction_deliveries "
            "WHERE owner_user_id=$1 AND session_id=$2 ORDER BY grader_id",
            owner,
            session_id,
        )
        rows = [dict(row) for row in existing]
        if any(
            row["source_format"] != source_format or row["repository"] != repository for row in rows
        ):
            raise InstructionInvalid(
                "Session instruction assignment already uses another harness or repository"
            )
        assigned = {row["grader_id"] for row in rows}
        releases = await conn.fetch(
            "SELECT r.* FROM rm_wb_instruction_heads h "
            "JOIN rm_wb_instruction_releases r ON r.id=h.release_id "
            "WHERE r.owner_user_id=$1 AND r.change_id IS NOT NULL ORDER BY r.grader_id",
            owner,
        )
        total = sum(len(instruction_context(row)) + 2 for row in rows)
        for release in releases:
            if release["grader_id"] in assigned or not _scope_matches(
                release["scope"], source_format, repository
            ):
                continue
            # Only sessions begun after this release are eligible. A resumed
            # pre-release session must not silently acquire new instructions.
            if session["started_at"] < release["created_at"]:
                continue
            # Bound context before creating an offer; skipped versions remain
            # available but have no purported per-run delivery record.
            expected_size = len(release["content"]) + 240
            if total + expected_size > MAX_CONTEXT_CHARS:
                continue
            row = await conn.fetchrow(
                "INSERT INTO rm_wb_instruction_deliveries "
                "(owner_user_id,grader_id,release_id,change_id,session_id,source_format,repository,content,content_sha256) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *",
                owner,
                release["grader_id"],
                release["id"],
                release["change_id"],
                session_id,
                source_format,
                repository,
                release["content"],
                release["content_sha256"],
            )
            rows.append(dict(row))
            total += expected_size
        return {
            "deliveries": rows,
            "additional_context": "\n\n".join(instruction_context(row) for row in rows),
        }


async def observe_trace(
    owner: UUID, session_id: str, trace_id: UUID, steps: list[dict] | None = None
) -> int:
    """Reconcile offers against saved native transcript context; safe to retry.

    Always read authoritative saved steps. The optional steps argument is
    accepted for callers already holding a trace, but never trusted as proof.
    """
    async with get_pool().acquire() as conn, conn.transaction():
        trace = await conn.fetchrow(
            "SELECT source_format FROM rm_traces WHERE id=$1 AND owner_user_id=$2 AND external_id=$3",
            trace_id,
            owner,
            session_id,
        )
        if not trace or trace["source_format"] not in {"codex", "claude_code"}:
            return 0
        context_steps = await conn.fetch(
            "SELECT id,role,content FROM rm_trace_steps "
            "WHERE trace_id=$1 AND role IN ('system','user') ORDER BY idx",
            trace_id,
        )
        rows = await conn.fetch(
            "SELECT * FROM rm_wb_instruction_deliveries "
            "WHERE owner_user_id=$1 AND session_id=$2 AND source_format=$3 AND status='offered' FOR UPDATE",
            owner,
            session_id,
            trace["source_format"],
        )
        captured = 0
        for row in rows:
            context = instruction_context(dict(row))
            step = next((s for s in context_steps if context in (s["content"] or "")), None)
            if not step:
                continue
            await conn.execute(
                "UPDATE rm_wb_instruction_deliveries SET status='captured',trace_id=$2,step_id=$3,captured_at=now() "
                "WHERE id=$1",
                row["id"],
                trace_id,
                step["id"],
            )
            captured += 1
        return captured


async def list_deliveries(owner: UUID, trace_id: UUID | None = None) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT d.* FROM rm_wb_instruction_deliveries d "
        "WHERE d.owner_user_id=$1 AND ($2::uuid IS NULL OR EXISTS "
        "(SELECT 1 FROM rm_traces t WHERE t.id=$2 AND t.owner_user_id=$1 AND t.external_id=d.session_id)) "
        "ORDER BY d.offered_at DESC,d.id LIMIT 200",
        owner,
        trace_id,
    )
    return [dict(row) for row in rows]


async def list_releases(owner: UUID, grader_id: UUID) -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT r.*, (h.release_id=r.id) AS active FROM rm_wb_instruction_releases r "
        "LEFT JOIN rm_wb_instruction_heads h ON h.grader_id=r.grader_id "
        "WHERE r.owner_user_id=$1 AND r.grader_id=$2 ORDER BY r.created_at DESC,r.id",
        owner,
        grader_id,
    )
    return [dict(row) for row in rows]
