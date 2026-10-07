"""Generate validated skill metadata without loading the GPU worker dependencies."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
MAX_IDENTITY_ATTEMPTS = 3
MAX_IDENTITY_CONVERSATION_CHARS = 1500
SKILL_IDENTITY_TOOL_NAME = "set_skill_identity"

SKILL_IDENTITY_PROMPT = """Human annotators reviewed conversations between users and an AI agent and
left the comments below. A skill (a SKILL.md the agent loads into its context) will be written to
teach the agent to behave the way the annotators rewarded. Name that skill and describe it.

Rules:
- "name": lowercase letters, digits and single hyphens only (for example "refund-requests"),
  at most 64 characters.
- "description": one brief sentence saying WHEN the agent should use the skill. Aim for at most
  256 characters; the hard limit is 1024 characters. Leave detailed behavioral instructions,
  examples, and procedures for the skill body, which will be written separately.

Call set_skill_identity with the name and description.

Annotated conversations:

<examples>"""

SKILL_IDENTITY_TOOL = {
    "type": "function",
    "function": {
        "name": SKILL_IDENTITY_TOOL_NAME,
        "description": "Set the skill's name and short usage description, not its instructions.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_SKILL_NAME_LENGTH,
                    "pattern": SKILL_NAME_PATTERN.pattern,
                    "description": "Lowercase letters, digits and single hyphens, at most 64 characters.",
                },
                "description": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_SKILL_DESCRIPTION_LENGTH,
                    "description": "One brief sentence saying when to use the skill; aim for at most 256 characters.",
                },
            },
            "required": ["name", "description"],
            "additionalProperties": False,
        },
    },
}


def _parse_identity(response: Any) -> tuple[str, str]:
    calls = response.choices[0].message.tool_calls
    if not calls or len(calls) != 1 or calls[0].function.name != SKILL_IDENTITY_TOOL_NAME:
        raise ValueError(f"call {SKILL_IDENTITY_TOOL_NAME} exactly once")
    arguments = calls[0].function.arguments
    if not isinstance(arguments, str):
        raise ValueError("tool arguments must be a JSON object")
    try:
        identity = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("tool arguments must be valid JSON") from exc
    if not isinstance(identity, dict) or set(identity) != {"name", "description"}:
        raise ValueError("tool arguments must contain exactly name and description")
    name, description = identity["name"], identity["description"]
    if not isinstance(name, str) or not isinstance(description, str):
        raise ValueError("name and description must be strings")
    name = name.strip()
    description = " ".join(description.split())
    if not SKILL_NAME_PATTERN.fullmatch(name) or len(name) > MAX_SKILL_NAME_LENGTH:
        raise ValueError(
            "name must use lowercase letters, digits and single hyphens, at most 64 characters"
        )
    if not 1 <= len(description) <= MAX_SKILL_DESCRIPTION_LENGTH:
        raise ValueError(
            f"description must be 1–{MAX_SKILL_DESCRIPTION_LENGTH} characters; got {len(description)}"
        )
    return name, description


def derive_skill_identity(
    reflection_model: str, examples: list[dict], *, complete: Callable[..., Any]
) -> tuple[str, str]:
    """Repair invalid model output with bounded retries; provider errors still propagate."""
    sections = []
    for number, example in enumerate(examples, start=1):
        conversation = "\n\n".join(
            f"{message['role']}: {message['content']}" for message in example["messages"]
        )[:MAX_IDENTITY_CONVERSATION_CHARS]
        comments = "\n".join(f"- {comment}" for comment in example["feedback"])
        sections.append(
            f"## Conversation {number}\n{conversation}\n\nAnnotator comments:\n{comments}"
        )
    prompt = SKILL_IDENTITY_PROMPT.replace("<examples>", "\n\n".join(sections))
    correction = ""
    for attempt in range(1, MAX_IDENTITY_ATTEMPTS + 1):
        response = complete(
            model=reflection_model,
            messages=[{"role": "user", "content": prompt + correction}],
            tools=[SKILL_IDENTITY_TOOL],
            tool_choice={"type": "function", "function": {"name": SKILL_IDENTITY_TOOL_NAME}},
        )
        try:
            return _parse_identity(response)
        except ValueError as exc:
            if attempt == MAX_IDENTITY_ATTEMPTS:
                raise ValueError(
                    f"Could not generate valid skill metadata after {attempt} attempts: {exc}. "
                    "Please retry skill creation."
                ) from exc
            logger.warning(
                "Skill metadata attempt %s failed validation: %s; retrying", attempt, exc
            )
            correction = (
                f"\n\nYour previous response failed validation: {exc}. "
                "Try again with a short name and a single concise usage sentence under 256 characters. "
                "Do not put skill instructions in the description. Call set_skill_identity."
            )
    raise AssertionError("skill metadata attempts must be positive")


def render_skill(name: str, description: str, body: str) -> str:
    # A valid description can contain colons, quotes, or YAML-looking text.
    # JSON strings are also valid YAML scalars and preserve the description exactly.
    return f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n{body}"
