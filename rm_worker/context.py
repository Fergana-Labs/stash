"""Versioned action inputs shared by the API and GPU worker; no ML imports."""

import json

PREFIX = "STASH_ACTION_V3\n"
SECTIONS = {
    "instructions": 24,
    "task": 14,
    "request": 14,
    "history": 22,
    "action": 20,
    "rubric": 6,
}
OMITTED = "\n[earlier or intervening content omitted]\n"


def clip(text: str, limit: int, *, tail: bool = False) -> str:
    if len(text) <= limit:
        return text
    if tail:
        return OMITTED + text[-limit:]
    half = limit // 2
    return text[:half] + OMITTED + text[-half:]


def action_text(step: dict) -> str:
    text = f"{step['role']}: {step.get('content') or ''}"
    if step.get("tool_name"):
        text += f"\nTool: {step['tool_name']}\nArguments: " + json.dumps(step.get("tool_input"))
    return text


def is_instruction(step: dict) -> bool:
    return step["role"] == "system" or (
        step["role"] == "user"
        and (step.get("content") or "").lstrip().startswith("# AGENTS.md instructions")
    )


def is_harness_message(step: dict) -> bool:
    return step["role"] == "user" and (step.get("content") or "").lstrip().startswith(
        ("<teammate-message", "<heartbeat>", "<external_codex_apps_")
    )


def action_context(steps: list[dict], rubric: list[str] | tuple[str, ...] = ()) -> dict[str, str]:
    if not steps or steps[-1]["role"] != "assistant":
        raise ValueError("An action input must end at the assistant action being judged")
    prior = steps[:-1]
    repo_rules = [s["content"] for s in prior if is_instruction(s) and s["role"] == "user"]
    system = [s["content"] for s in prior if s["role"] == "system"]
    user_turns = [
        s["content"]
        for s in prior
        if s["role"] == "user"
        and not is_instruction(s)
        and not s["content"].lstrip().startswith("<external_codex_apps_")
    ]
    requests = [
        s["content"]
        for s in prior
        if s["role"] == "user" and not is_instruction(s) and not is_harness_message(s)
    ]
    # A subagent may receive its entire task in a teammate envelope. Retain the
    # initial assignment in that case, without promoting later status pings.
    assignments = [text for text in user_turns if text.lstrip().startswith("<teammate-message")]
    requests = requests or assignments[:1] or user_turns[:1]
    # Preserve the most recent repo instructions separately from the much larger
    # harness prompt. Updated AGENTS.md blocks replace their earlier versions.
    instructions = "\n\n".join([*repo_rules[-1:], *system])
    history = []
    remaining = 24000
    for step in reversed(prior):
        if is_instruction(step):
            continue
        text = action_text(step)
        history.append(clip(text, remaining, tail=True))
        remaining -= len(text)
        if remaining <= 0:
            break
    return {
        "instructions": clip(instructions, 16000),
        "task": clip(requests[0], 8000) if requests else "",
        "request": clip(requests[-1], 8000) if requests else "",
        "history": "\n\n".join(reversed(history)),
        "action": clip(action_text(steps[-1]), 12000),
        "rubric": "\n".join(rubric),
    }


def render_action_input(steps: list[dict], rubric: list[str] | tuple[str, ...] = ()) -> str:
    return PREFIX + json.dumps(action_context(steps, rubric), ensure_ascii=True)


def encode_action_input(tokenizer, text: str) -> list[int]:
    """Fixed section budgets keep the task and instructions alongside recent tools.

    The budgets do not depend on a candidate's length: a longer alternative must
    not evict context that was visible to the other side of a preference pair.
    """
    if not text.startswith(PREFIX):
        raise ValueError("This checkpoint requires Stash action input version 3")
    data = json.loads(text[len(PREFIX) :])
    if set(data) != set(SECTIONS) or not all(isinstance(v, str) for v in data.values()):
        raise ValueError("Invalid version 3 action sections")
    headers = {key: tokenizer.encode(f"\n[{key}]\n", add_special_tokens=False) for key in SECTIONS}
    overhead = sum(map(len, headers.values())) + tokenizer.num_special_tokens_to_add(pair=False)
    # Reserve room for re-tokenizing section boundaries through the public API.
    available = tokenizer.model_max_length - overhead - min(32, tokenizer.model_max_length // 8)
    if available < len(SECTIONS):
        raise ValueError("Context window is too small for action sections")
    ids = []
    for key, weight in SECTIONS.items():
        budget = max(1, available * weight // 100)
        content = tokenizer.encode(data[key], add_special_tokens=False)
        if len(content) > budget:
            # Mark omissions explicitly, including inside an oversized action.
            marker = tokenizer.encode(" [omitted] ", add_special_tokens=False)[:budget]
            keep = budget - len(marker)
            head = 0 if key == "history" else keep // 2
            tail = keep - head
            content = content[:head] + marker + (content[-tail:] if tail else [])
        ids.extend(headers[key])
        ids.extend(content)
    rendered = tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
    encoded = tokenizer.encode(rendered, add_special_tokens=True)
    if len(encoded) > tokenizer.model_max_length:
        raise ValueError("Encoded action exceeds the checkpoint context window")
    return encoded
