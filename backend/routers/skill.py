from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["skill"])

SKILL_PATH = Path(__file__).parent.parent / "static" / "SKILL.md"


@router.get("/skill/octopus/SKILL.md", response_class=PlainTextResponse)
async def get_skill_manifest():
    return SKILL_PATH.read_text()
