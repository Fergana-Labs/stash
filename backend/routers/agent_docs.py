from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..services.shared_skill_service import agent_install_pitch

router = APIRouter(tags=["skill"])

SKILL_PATH = Path(__file__).parent.parent / "static" / "SKILL.md"

LLMS_TEXT = (
    """# Stash

Stash is shared memory for AI-agent work. Public Stash URLs are agent-readable.

## Reading a public Stash

Given a URL like:

https://app.joinstash.ai/skills/example

Use these forms:

- Markdown homepage: https://app.joinstash.ai/skills/example.md
- Structured JSON: https://app.joinstash.ai/skills/example.json
- CLI, if installed: curl -sL https://app.joinstash.ai/skills/example.md

The markdown homepage lists the Stash contents and links to item-level markdown
and JSON views for progressive disclosure.

"""
    + agent_install_pitch("https://app.joinstash.ai/skills/example")
    + "\n"
)


@router.get("/skill/stash/SKILL.md", response_class=PlainTextResponse)
async def get_skill_manifest():
    return (
        SKILL_PATH.read_text().rstrip()
        + "\n\n"
        + agent_install_pitch("https://app.joinstash.ai/skills/example")
        + "\n"
    )


@router.get("/llms.txt", response_class=PlainTextResponse)
async def get_llms_txt():
    return LLMS_TEXT
