"""Web-onboarding choices that the CLI applies at signin.

The web onboarding page stores the user's setup choices here. The next
interactive `stash signin` on their machine reads them, applies them while
printing one line per choice, and marks them consumed — so a later
standalone signin runs the interactive wizard instead of silently
re-applying stale web choices.
"""

from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..database import get_pool

router = APIRouter(prefix="/api/v1", tags=["onboarding"])

# Mirrors _SUPPORTED_AGENTS in cli/main.py — the CLI is what applies the
# choice, so the web must not offer an agent the CLI can't record.
KNOWN_AGENTS = {"claude", "cursor", "codex", "opencode", "gemini", "openclaw", "hermes"}

# The exact CLAUDE.md block `stash connect` appends. The file lives in the
# CLI package (cli/main.py reads it too) and is COPY'd into the backend image,
# so the web preview and the terminal append the same bytes.
CLAUDE_MD_BLOCK_PATH = Path(__file__).resolve().parent.parent.parent / "cli" / "claude_md_block.md"


class OnboardingPreferences(BaseModel):
    enabled_agents: list[str] = Field(max_length=len(KNOWN_AGENTS))
    record_scope: Literal["everything", "selected_folders"]
    import_history: bool
    claude_md_opt_in: bool


@router.get("/me/onboarding-preferences")
async def get_onboarding_preferences(current_user: dict = Depends(get_current_user)) -> dict:
    row = await get_pool().fetchrow(
        "SELECT enabled_agents, record_scope, import_history, claude_md_opt_in, consumed_at "
        "FROM onboarding_preferences WHERE user_id = $1",
        current_user["id"],
    )
    if row is None:
        return {"preferences": None}
    return {
        "preferences": {
            "enabled_agents": list(row["enabled_agents"]),
            "record_scope": row["record_scope"],
            "import_history": row["import_history"],
            "claude_md_opt_in": row["claude_md_opt_in"],
            "consumed_at": row["consumed_at"].isoformat() if row["consumed_at"] else None,
        }
    }


@router.put("/me/onboarding-preferences")
async def put_onboarding_preferences(
    prefs: OnboardingPreferences, current_user: dict = Depends(get_current_user)
) -> dict:
    unknown = sorted(set(prefs.enabled_agents) - KNOWN_AGENTS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown agents: {', '.join(unknown)}")
    # New choices supersede an already-consumed set: consumed_at resets so the
    # next signin applies them.
    await get_pool().execute(
        """
        INSERT INTO onboarding_preferences
            (user_id, enabled_agents, record_scope, import_history, claude_md_opt_in)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO UPDATE SET
            enabled_agents = EXCLUDED.enabled_agents,
            record_scope = EXCLUDED.record_scope,
            import_history = EXCLUDED.import_history,
            claude_md_opt_in = EXCLUDED.claude_md_opt_in,
            consumed_at = NULL,
            updated_at = now()
        """,
        current_user["id"],
        prefs.enabled_agents,
        prefs.record_scope,
        prefs.import_history,
        prefs.claude_md_opt_in,
    )
    return {"ok": True}


@router.post("/me/onboarding-preferences/consume")
async def consume_onboarding_preferences(current_user: dict = Depends(get_current_user)) -> dict:
    user_id: UUID = current_user["id"]
    result = await get_pool().execute(
        "UPDATE onboarding_preferences SET consumed_at = now() WHERE user_id = $1", user_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="No onboarding preferences to consume")
    return {"ok": True}


@router.get("/claude-md-block")
async def get_claude_md_block() -> dict:
    """The exact block `stash connect` appends to CLAUDE.md, for the web
    onboarding preview. Public text — it ends up in users' repos verbatim."""
    return {"block": CLAUDE_MD_BLOCK_PATH.read_text()}
