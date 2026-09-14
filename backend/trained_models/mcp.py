"""The MCP tools a trained-model kind gives an agent.

Served by `skill_servers` at /mcp/<kind>; this module only decides what the
tools are. The generic ones (status, corpus, training, jobs, housekeeping)
are the same for every kind; the kind adds its own operations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from mcp.server.fastmcp import FastMCP

from ..skill_servers.tools import current_user, new_server
from . import registry, service


def _generic_tools(mcp: FastMCP, kind: str) -> None:
    @mcp.tool()
    async def setup_status() -> dict:
        """Call this first. Which models exist and their state, whether a paid
        training run is waiting to be used, and the next step to take."""
        user = current_user()
        return await service.setup_status(user["id"], user, kind)

    @mcp.tool()
    async def check_corpus(folder: str) -> dict:
        """Judge a folder of the user's writing before training. Free and
        instant. Reports usable words, what was ignored, duplicates, and any
        blocker. `folder` is a folder name or id in the user's Files."""
        user = current_user()
        try:
            report, folder_row = await service.check_corpus(user["id"], user["id"], kind, folder)
        except (service.FolderNotFound, service.AmbiguousFolder) as error:
            return {"status": "error", "message": str(error)}
        return {
            "folder": {"id": str(folder_row["id"]), "name": folder_row["name"]},
            **report.to_dict(),
        }

    @mcp.tool()
    async def train(name: str, folder: str) -> dict:
        """Start a training run on a folder of the user's writing. Returns the
        queued model, or `payment_required` with a checkout link the user must
        open and pay (one-time fee per run) — relay the link, wait for them to
        say they've paid, then call train again with the same arguments.
        Poll job_result until the model is ready; about six minutes."""
        user = current_user()
        try:
            model = await service.train(user["id"], user, kind, name, folder)
        except service.PaymentRequired as error:
            return {
                "status": "payment_required",
                "fee": f"${error.amount_cents // 100} one-time, then unlimited use",
                "checkout_url": error.checkout_url,
                "hint": "Give the user this link. Once they've paid, call train again.",
            }
        except service.CorpusNotReady as error:
            return {"status": "corpus_not_ready", **error.report.to_dict()}
        except (
            service.FolderNotFound,
            service.AmbiguousFolder,
            service.NameTaken,
            service.BadName,
        ) as error:
            return {"status": "error", "message": str(error)}
        return {"status": model["status"], "model": service.public(model)}

    @mcp.tool()
    async def job_result(model: str, job_id: str | None = None) -> dict:
        """Progress of a training run (omit job_id) or of a generation that
        came back pending (pass its job_id)."""
        user = current_user()
        try:
            if job_id is None:
                return {"model": service.public(await service.get_model(user["id"], kind, model))}
            return await service.job_result(user["id"], kind, model, job_id)
        except service.ModelNotFound as error:
            return {"status": "error", "message": str(error)}

    @mcp.tool()
    async def list_models() -> list[dict]:
        """Every model of this kind the user has, with status."""
        return [service.public(m) for m in await service.list_models(current_user()["id"], kind)]

    @mcp.tool()
    async def delete_model(name: str) -> dict:
        """Delete a model. Only on the user's explicit say-so; it cannot be
        undone and a new one costs a training run."""
        try:
            deleted = await service.delete_model(current_user()["id"], kind, name)
        except service.BadName as error:
            return {"status": "error", "message": str(error)}
        return {"deleted": deleted}


def _run_for(kind: str) -> Callable[[str, str, dict], Awaitable[dict]]:
    async def run_op(model: str, op: str, payload: dict) -> dict:
        user = current_user()
        try:
            return await service.run(user["id"], kind, model, op, payload)
        except (service.ModelNotFound, service.ModelNotReady, ValueError) as error:
            return {"status": "error", "message": str(error)}

    return run_op


def build(kind: str) -> FastMCP:
    module = registry.get(kind)
    mcp = new_server(
        kind,
        f"{module.TITLE}: models trained on the user's own material. Call setup_status first.",
    )
    _generic_tools(mcp, kind)
    module.register_tools(mcp, _run_for(kind))
    return mcp
