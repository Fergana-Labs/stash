"""What every kind of trained model shares: the corpus is a folder, a run
costs one purchase, a model row moves queued → training → ready or failed,
and a ready model answers operations.

Payment is decided in exactly one place, `train`, and expressed as an
exception carrying the checkout URL. The page, the MCP tools and the agent
all relay that same URL; nothing else asks "is this paid".
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from ..config import settings
from ..database import get_pool
from ..services import billing_service, files_tree_service
from . import gpu, purchases, registry
from .kinds.stylewriter.corpus import CorpusReport, Document

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

# A training run that has not reported back by then is treated as lost and
# its purchase handed back. Cold image builds and model downloads can take a
# while on the first run in a fresh workspace, so this is generous.
MAX_TRAINING = timedelta(hours=2)

_MODEL_COLUMNS = (
    "id, owner_user_id, kind, name, status, purchase_id, corpus_folder_id, corpus, words, "
    "base_model, job_ref, provider_ref, profile, error, created_at, trained_at"
)


class PaymentRequired(Exception):
    def __init__(self, checkout_url: str, amount_cents: int):
        super().__init__("A training run must be purchased first")
        self.checkout_url = checkout_url
        self.amount_cents = amount_cents


class CorpusNotReady(Exception):
    def __init__(self, report: CorpusReport):
        super().__init__("; ".join(report.reasons))
        self.report = report


class FolderNotFound(Exception):
    pass


class AmbiguousFolder(Exception):
    pass


class ModelNotFound(Exception):
    pass


class ModelNotReady(Exception):
    pass


class NameTaken(Exception):
    pass


class BadName(Exception):
    pass


def public(model: dict) -> dict:
    """The row as callers see it: no adapter path, no style profile."""
    return {
        "id": str(model["id"]),
        "kind": model["kind"],
        "name": model["name"],
        "status": model["status"],
        "words": model["words"],
        "base_model": model["base_model"],
        "corpus_folder_id": str(model["corpus_folder_id"]) if model["corpus_folder_id"] else None,
        "corpus": model["corpus"],
        "error": model["error"],
        "created_at": model["created_at"].isoformat(),
        "trained_at": model["trained_at"].isoformat() if model["trained_at"] else None,
    }


# ── Models ────────────────────────────────────────────────────────────


async def list_models(owner_user_id: UUID, kind: str | None = None) -> list[dict]:
    pool = get_pool()
    if kind is None:
        rows = await pool.fetch(
            f"SELECT {_MODEL_COLUMNS} FROM trained_models WHERE owner_user_id = $1 "
            "ORDER BY created_at",
            owner_user_id,
        )
    else:
        rows = await pool.fetch(
            f"SELECT {_MODEL_COLUMNS} FROM trained_models "
            "WHERE owner_user_id = $1 AND kind = $2 ORDER BY created_at",
            owner_user_id,
            kind,
        )
    return [dict(r) for r in rows]


async def get_model(owner_user_id: UUID, kind: str, name: str) -> dict:
    row = await get_pool().fetchrow(
        f"SELECT {_MODEL_COLUMNS} FROM trained_models "
        "WHERE owner_user_id = $1 AND kind = $2 AND name = $3",
        owner_user_id,
        kind,
        name,
    )
    if row is None:
        raise ModelNotFound(f"no {kind} model named {name!r}")
    return dict(row)


async def get_model_by_id(model_id: UUID) -> dict | None:
    row = await get_pool().fetchrow(
        f"SELECT {_MODEL_COLUMNS} FROM trained_models WHERE id = $1", model_id
    )
    return dict(row) if row else None


async def delete_model(owner_user_id: UUID, kind: str, name: str) -> bool:
    """Drop the row. The adapter on the GPU volume is small and is reaped by
    the GPU app's own housekeeping, not by a request."""
    status = await get_pool().execute(
        "DELETE FROM trained_models WHERE owner_user_id = $1 AND kind = $2 AND name = $3",
        owner_user_id,
        kind,
        name,
    )
    return status == "DELETE 1"


# ── Corpus ────────────────────────────────────────────────────────────


async def resolve_folder(owner_user_id: UUID, user_id: UUID, folder: str) -> dict:
    """A folder by id or by exact name among the folders this user can read.
    Two folders with the same name is a real ambiguity, so it is reported
    rather than resolved by guessing."""
    readable = await files_tree_service.list_folders(owner_user_id, user_id)
    try:
        wanted = UUID(folder)
    except ValueError:
        wanted = None
    if wanted is not None:
        by_id = [f for f in readable if f["id"] == wanted]
        if not by_id:
            raise FolderNotFound(f"no folder with id {folder}")
        return by_id[0]
    by_name = [f for f in readable if f["name"] == folder]
    if not by_name:
        raise FolderNotFound(f"no folder named {folder!r}")
    if len(by_name) > 1:
        ids = ", ".join(str(f["id"]) for f in by_name)
        raise AmbiguousFolder(f"{len(by_name)} folders are named {folder!r}; pass an id: {ids}")
    return by_name[0]


async def folder_documents(folder_id: UUID) -> list[Document]:
    """Every page in the folder and its subfolders, as text. Uploaded files
    are not read: the corpus is pages, and the page is the unit a person
    or an agent adds writing as."""
    folder_ids = await files_tree_service.folder_subtree_ids(folder_id)
    rows = await get_pool().fetch(
        "SELECT name, content_type, content_markdown, content_html FROM pages "
        "WHERE folder_id = ANY($1::uuid[]) AND deleted_at IS NULL ORDER BY name",
        list(folder_ids),
    )
    return [
        Document(
            name=r["name"],
            text=(r["content_markdown"] if r["content_type"] == "markdown" else r["content_html"])
            or "",
        )
        for r in rows
    ]


async def check_corpus(
    owner_user_id: UUID, user_id: UUID, kind: str, folder: str
) -> tuple[CorpusReport, dict]:
    module = registry.get(kind)
    folder_row = await resolve_folder(owner_user_id, user_id, folder)
    report = module.check_corpus(await folder_documents(folder_row["id"]))
    return report, folder_row


def _corpus_record(report: CorpusReport) -> dict:
    """What was trained on, kept with the model so a later edit of the folder
    never changes the record of this run."""
    return {
        "usable_words": report.usable_words,
        "chunks": len(report.chunks),
        "sources": sorted({c.source for c in report.chunks}),
    }


# ── Training ──────────────────────────────────────────────────────────


def payment_required(user: dict) -> bool:
    """Self-hosted instances and internal accounts train for free; the same
    rule the Pro gate uses."""
    if not billing_service.billing_enabled():
        return False
    return not billing_service.is_internal_email(user.get("email"))


def price_id(kind: str) -> str:
    module = registry.get(kind)
    value = getattr(settings, module.PRICE_SETTING)
    if not value:
        raise RuntimeError(f"{module.PRICE_SETTING} is not set; create the Stripe price first")
    return value


async def train(owner_user_id: UUID, user: dict, kind: str, name: str, folder: str) -> dict:
    """Queue one training run. Raises before anything is written when the
    name is bad or taken, the corpus is not ready, or a purchase is needed.

    The purchase is consumed and the row written in one transaction, and the
    GPU job is only started once that holds: a job that failed to start
    hands the purchase straight back rather than leaving it half spent."""
    module = registry.get(kind)
    if not NAME_RE.match(name):
        raise BadName("names are 1-40 characters of lowercase letters, digits and hyphens")
    if await _name_exists(owner_user_id, kind, name):
        raise NameTaken(f"a {kind} model named {name!r} already exists")

    report, folder_row = await check_corpus(owner_user_id, user["id"], kind, folder)
    if not report.ready:
        raise CorpusNotReady(report)

    purchase_id: UUID | None = None
    if payment_required(user):
        purchase_id = await purchases.spendable(owner_user_id, kind)
        if purchase_id is None:
            url = await billing_service.create_purchase_checkout(
                user, owner_user_id, kind, price_id(kind)
            )
            raise PaymentRequired(url, billing_service.TRAINING_PRICE_CENTS)

    model_id = uuid.uuid4()
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        if purchase_id is not None:
            consumed = await conn.fetchval(
                "UPDATE training_purchases SET consumed_by = $1 "
                "WHERE id = $2 AND consumed_by IS NULL RETURNING id",
                model_id,
                purchase_id,
            )
            if consumed is None:
                raise RuntimeError("the purchase was spent by a concurrent training run")
        await conn.execute(
            """
            INSERT INTO trained_models
                (id, owner_user_id, kind, name, status, purchase_id, corpus_folder_id,
                 corpus, words, base_model)
            VALUES ($1, $2, $3, $4, 'queued', $5, $6, $7, $8, $9)
            """,
            model_id,
            owner_user_id,
            kind,
            name,
            purchase_id,
            folder_row["id"],
            _corpus_record(report),
            report.usable_words,
            module.BASE_MODEL,
        )

    try:
        job_ref = await module.start_training(f"model_{model_id.hex}", report)
    except Exception:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM trained_models WHERE id = $1", model_id)
            await conn.execute(
                "UPDATE training_purchases SET consumed_by = NULL WHERE consumed_by = $1", model_id
            )
        raise
    await pool.execute(
        "UPDATE trained_models SET status = 'training', job_ref = $2 WHERE id = $1",
        model_id,
        job_ref,
    )

    from . import tasks

    tasks.poll_training.delay(str(model_id))
    return await get_model_by_id(model_id)


async def _name_exists(owner_user_id: UUID, kind: str, name: str) -> bool:
    return await get_pool().fetchval(
        "SELECT EXISTS (SELECT 1 FROM trained_models "
        "WHERE owner_user_id = $1 AND kind = $2 AND name = $3)",
        owner_user_id,
        kind,
        name,
    )


async def mark_ready(model_id: UUID, result: dict) -> None:
    await get_pool().execute(
        """
        UPDATE trained_models
        SET status = 'ready', provider_ref = $2, profile = $3, trained_at = now(), job_ref = NULL
        WHERE id = $1 AND status = 'training'
        """,
        model_id,
        result["adapter_path"],
        result["profile"],
    )


async def mark_failed(model_id: UUID, error: str) -> None:
    """The run is over and produced nothing, so the purchase is spendable
    again. `error` is shown to the owner; keep it to the class of failure."""
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE trained_models SET status = 'failed', error = $2, job_ref = NULL "
            "WHERE id = $1 AND status = 'training'",
            model_id,
            error[:500],
        )
        await conn.execute(
            "UPDATE training_purchases SET consumed_by = NULL WHERE consumed_by = $1", model_id
        )


async def advance_training(model_id: UUID) -> str:
    """One poll of a training run. Returns the model's status afterwards."""
    model = await get_model_by_id(model_id)
    if model is None or model["status"] != "training":
        return "gone" if model is None else model["status"]
    module = registry.get(model["kind"])
    try:
        found = await module.training_result(model["job_ref"])
    except gpu.GpuJobFailed as error:
        await mark_failed(model_id, f"training failed: {error}")
        return "failed"
    if found is not None:
        await mark_ready(model_id, found)
        return "ready"
    if datetime.now(UTC) - model["created_at"] > MAX_TRAINING:
        await mark_failed(model_id, "training did not finish in time")
        return "failed"
    return "training"


# ── Using a model ─────────────────────────────────────────────────────


async def run(owner_user_id: UUID, kind: str, name: str, op: str, payload: dict) -> dict:
    module = registry.get(kind)
    if op not in module.OPS:
        raise ValueError(f"unknown operation {op!r}; {kind} supports {', '.join(module.OPS)}")
    parsed = module.OPS[op].model_validate(payload)
    model = await get_model(owner_user_id, kind, name)
    if model["status"] != "ready":
        raise ModelNotReady(f"model {name!r} is {model['status']}, not ready")
    return await module.run(model, op, parsed)


async def job_result(owner_user_id: UUID, kind: str, name: str, job_id: str) -> dict:
    module = registry.get(kind)
    model = await get_model(owner_user_id, kind, name)
    return await module.job_result(model, job_id)


async def setup_status(owner_user_id: UUID, user: dict, kind: str) -> dict:
    """Where this user is with this kind of model, and what to do next."""
    module = registry.get(kind)
    models = [public(m) for m in await list_models(owner_user_id, kind)]
    ready = [m["name"] for m in models if m["status"] == "ready"]
    training = [m["name"] for m in models if m["status"] in ("queued", "training")]
    spendable = await purchases.spendable_count(owner_user_id, kind)
    if ready:
        next_step = f"Ready to write with: {', '.join(ready)}."
    elif training:
        next_step = f"Training: {', '.join(training)}. Poll job_result until ready."
    elif spendable:
        next_step = "A training run is paid for. Put the writing in a folder and call train."
    elif payment_required(user):
        next_step = (
            "Put the user's writing in a folder, check it with check_corpus, then call "
            "train — it returns a checkout link for the one-time training fee."
        )
    else:
        next_step = "Put the user's writing in a folder, check it with check_corpus, then train."
    return {
        "kind": kind,
        "title": module.TITLE,
        "models": models,
        "paid_runs_available": spendable,
        "training_fee": None
        if not payment_required(user)
        else f"${billing_service.TRAINING_PRICE_CENTS // 100} per training run, unlimited use",
        "next_step": next_step,
    }
