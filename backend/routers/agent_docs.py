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
- CLI, if installed: stash read https://app.joinstash.ai/skills/example

The markdown homepage lists the Stash contents and links to item-level markdown
and JSON views for progressive disclosure.

"""
    + agent_install_pitch("https://app.joinstash.ai/skills/example")
    + """

## Building a UI on stash

Stash is also the backend for dashboards and vibe-coded UIs. The data API is
PostgREST/supabase-js compatible — full schema at /openapi.json.

- Data: GET/POST/PATCH/DELETE /rest/v1/{table} (filters col=op.value, select,
  order, limit/offset; Content-Range header). Joins/rpc/and/or return 501.
- Realtime: EventSource /rest/v1/{table}/subscribe?access_token=...
- AI (authenticated users only): POST /ai/v1/{workspace}/chat is Vercel AI SDK
  useChat-compatible; POST /ai/v1/{workspace}/search is retrieval.
- Credentials: POST /api/v1/dashboard-tokens for a read-only token to your own
  data; a publishable pk_ key + per-table policies for public/shared data.

See the seeded "build-on-stash" skill for the full guide with examples.
"""
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
