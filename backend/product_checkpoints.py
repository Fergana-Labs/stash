"""Operator-managed product experiences; account data stays with its owner."""

from typing import Literal

ProductCheckpoint = Literal["latest", "floodgate-2026-10-05"]


def has_workbench(user) -> bool:
    return (
        bool(user.get("reward_models_enabled"))
        and user.get("product_checkpoint", "latest") == "latest"
    )
