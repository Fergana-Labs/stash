"""Turn a one-paragraph request ("I want a skill that…") into a real Skill.

The request goes to Claude with a strict brief; the draft comes back as
name + description + instructions and is created as an ordinary folder-backed
Skill the user can edit. Co-creation is the point: the user sees a concrete
draft to react to instead of an empty form."""

from __future__ import annotations

from uuid import UUID

from . import files_tree_service, llm, skill_service

MAX_REQUEST_LENGTH = 2000

_SYSTEM = """\
You write SKILL.md files for coding agents (Claude Code, Codex, Cursor).
A Skill is a short, concrete playbook an agent follows when a task matches
its description. Write for an agent, not a human reader: imperative steps,
exact commands where they apply, explicit output formats, and rules that
prevent the common mistakes.

Return ONLY a JSON object with these keys:
- "name": a short title, at most 5 words, no trailing period.
- "description": one or two sentences saying what the skill does and when to
  use it. Start the second sentence with "Use when".
- "instructions": the Markdown body of the SKILL.md. 120-400 words. Use ##
  headings and numbered or bulleted lists. No frontmatter, no top-level
  title heading, no preamble about what a skill is."""


async def create_requested_skill(owner_user_id: UUID, created_by: UUID, request: str) -> dict:
    draft = await llm.complete_json(
        prompt=f"The user's request:\n\n{request.strip()}",
        system=_SYSTEM,
        tier=llm.ModelTier.QUALITY,
        max_tokens=2048,
    )
    name = _text_field(draft, "name")[: skill_service.MAX_SKILL_NAME_LENGTH]
    description = _text_field(draft, "description")[: skill_service.MAX_SKILL_DESCRIPTION_LENGTH]
    instructions = _text_field(draft, "instructions")
    return await files_tree_service.create_skill(
        owner_user_id, created_by, name, description, instructions
    )


def _text_field(draft: dict, key: str) -> str:
    value = draft.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"The Skill draft is missing its {key}")
    return value.strip()
