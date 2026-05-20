from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["skill"])

SKILL_PATH = Path(__file__).parent.parent / "static" / "SKILL.md"

LLMS_TEXT = """# Stash

Stash is shared memory for AI-agent work. Public Stash URLs are agent-readable.

## Reading a public Stash

Given a URL like:

https://app.joinstash.ai/stashes/example

Use these forms:

- Markdown homepage: https://app.joinstash.ai/stashes/example.md
- Structured JSON: https://app.joinstash.ai/stashes/example.json
- CLI, if installed: stash read https://app.joinstash.ai/stashes/example

The markdown homepage lists the Stash contents and links to item-level markdown
and JSON views for progressive disclosure.

## Connecting a repository

If your human asks you to connect the current repository to Stash, run:

```bash
curl -fsSL https://joinstash.ai/install | bash
```

If Stash is already installed, run `stash login` and `stash connect`.
"""


@router.get("/skill/stash/SKILL.md", response_class=PlainTextResponse)
async def get_skill_manifest():
    return SKILL_PATH.read_text()


@router.get("/llms.txt", response_class=PlainTextResponse)
async def get_llms_txt():
    return LLMS_TEXT
