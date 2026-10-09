"""Bounded, explicitly excerpted context without dropping annotation targets."""

from collections.abc import Iterator

from . import step_labeler


def window(chunks: list[dict], start: int, end: int, limit: int) -> list[dict]:
    """Keep neighboring steps and the most recent preceding user request.

    Chunk IDs remain global, so verdicts and task boundaries still refer to the
    original trace. No single overall task is assumed.
    """
    spare = max(0, limit - (end - start))
    left = max(0, start - spare // 2)
    right = min(len(chunks), end + spare - (start - left))
    left = max(0, left - (limit - (right - left)))
    selected = list(chunks[left:right])
    if left > 0 and spare:
        previous = next((c for c in reversed(chunks[:left]) if c["actor"] == "user"), None)
        if previous is not None:
            # Replace an outer neighbor, never a target.
            if left < start:
                selected[0] = previous
            elif right > end:
                selected = [previous, *selected[:-1]]
    return selected


def render(chunks: list[dict], budget: int, *, partial: bool = False) -> str:
    """Share the character budget fairly; retain small messages in full."""
    notice = (
        "[Excerpt of a longer trace. Original chunk IDs are retained. Omitted "
        "content is not evidence of failure or success; do not infer unseen work.]\n\n"
        if partial
        else ""
    )
    budget = max(0, budget)
    if not chunks or budget <= len(notice):
        return notice[:budget]
    available = budget - len(notice) - 2 * (len(chunks) - 1)
    # Cap each field before building strings, including user/assistant text.
    rendered = [step_labeler.render_chunk(c, budget) for c in chunks]
    allocations = [0] * len(chunks)
    remaining = max(0, available)
    for count, index in enumerate(sorted(range(len(chunks)), key=lambda i: len(rendered[i]))):
        share = remaining // (len(chunks) - count)
        allocations[index] = min(len(rendered[index]), share)
        remaining -= allocations[index]
    return (
        notice
        + "\n\n".join(step_labeler.clip(text, allocations[i]) for i, text in enumerate(rendered))
    )[:budget]


def batches(
    chunks: list[dict], chunk_budget: int, char_budget: int
) -> Iterator[tuple[list[dict], str]]:
    """Every chunk is a target exactly once, with overlapping context windows."""
    limit = max(1, chunk_budget)
    overlap = min(8, (limit - 1) // 4)
    width = max(1, limit - overlap * 2)
    if len(chunks) <= limit:
        yield chunks, render(chunks, char_budget)
        return
    for start in range(0, len(chunks), width):
        end = min(len(chunks), start + width)
        context = window(chunks, start, end, limit)
        yield chunks[start:end], render(context, char_budget, partial=True)
