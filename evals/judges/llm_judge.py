"""LLM-as-judge using Claude for qualitative evaluation.

Used for:
  - Retrieval relevance verification (spot-check when grades are unavailable)
  - Sleep agent curation quality (accuracy, completeness, no hallucination)
  - End-to-end context usefulness scoring
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from evals.config import cfg

_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import anthropic

            _client = anthropic.AsyncAnthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=cfg.judge_timeout_s,
            )
        except ImportError as exc:
            raise ImportError(
                "anthropic package required for LLM judge: pip install anthropic"
            ) from exc
    return _client


@dataclass
class JudgeScore:
    score: float          # 0.0 – 1.0
    verdict: str          # one-word verdict, e.g. "accurate", "hallucinated"
    reasoning: str        # brief explanation
    raw: dict[str, Any]   # full model response


async def judge_retrieval_relevance(
    query: str, page_name: str, page_content: str
) -> JudgeScore:
    """Score 0–3: how relevant is this page to the query?"""
    prompt = f"""You are evaluating information retrieval quality.

Query: {query}

Retrieved page title: {page_name}
Retrieved page content (first 400 chars): {page_content[:400]}

Score the relevance on a scale of 0–3:
  3 = Highly relevant: directly answers the query
  2 = Relevant: related and helpful context
  1 = Marginally relevant: loosely related
  0 = Not relevant: unrelated

Respond with JSON only:
{{"score": <0-3>, "verdict": "<one word>", "reasoning": "<one sentence>"}}"""

    return await _call_judge(prompt, max_score=3)


async def judge_curation_quality(
    source_events: list[str],
    created_note_name: str,
    created_note_content: str,
) -> JudgeScore:
    """Score 0–1: quality of a sleep-agent-created notebook note."""
    events_text = "\n".join(f"- {e}" for e in source_events[:10])
    prompt = f"""You are evaluating the quality of an AI agent's knowledge curation.

Source events the agent observed:
{events_text}

Note created by the agent:
Title: {created_note_name}
Content: {created_note_content[:600]}

Evaluate on these criteria (each 0–1):
1. accuracy: does the note accurately reflect what happened in the events?
2. completeness: does it capture all important information?
3. concision: is it appropriately brief (not over-padded)?
4. no_hallucination: does it avoid inventing facts not in the events?

Respond with JSON only:
{{
  "accuracy": <0-1>,
  "completeness": <0-1>,
  "concision": <0-1>,
  "no_hallucination": <0-1>,
  "overall": <0-1>,
  "verdict": "<one word: excellent|good|mediocre|poor>",
  "reasoning": "<one sentence>"
}}"""

    return await _call_judge(prompt, max_score=1, score_key="overall")


async def judge_context_usefulness(
    task: str,
    injected_pages: list[dict],
    expected_answer_hint: str,
) -> JudgeScore:
    """Score 0–1: would the injected context help answer this task?"""
    pages_text = "\n\n".join(
        f"### {p['name']}\n{p['content'][:300]}" for p in injected_pages[:5]
    )
    prompt = f"""You are evaluating an AI memory system.

Task the agent needs to perform: {task}

Context injected from memory:
{pages_text}

Expected answer hint: {expected_answer_hint}

Would the injected context meaningfully help the agent answer the task?

Respond with JSON only:
{{
  "helpful": <true|false>,
  "score": <0.0-1.0>,
  "verdict": "<one word: excellent|good|partial|useless>",
  "reasoning": "<one sentence>"
}}"""

    return await _call_judge(prompt, max_score=1)


async def judge_relation_quality(
    source_page: str,
    target_page: str,
    relation_type: str,
    source_content: str,
    target_content: str,
) -> JudgeScore:
    """Score 0–1: is this knowledge graph relation correct?"""
    prompt = f"""You are evaluating a knowledge graph relation extracted by an AI agent.

Source page: "{source_page}"
Content: {source_content[:300]}

Target page: "{target_page}"
Content: {target_content[:300]}

Extracted relation: {relation_type}

Is this relation correct, meaningful, and supported by the page content?

Respond with JSON only:
{{
  "score": <0.0-1.0>,
  "verdict": "<one word: correct|plausible|wrong|irrelevant>",
  "reasoning": "<one sentence>"
}}"""

    return await _call_judge(prompt, max_score=1)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _call_judge(
    prompt: str,
    max_score: float = 1.0,
    score_key: str = "score",
) -> JudgeScore:
    client = _get_client()
    message = await client.messages.create(
        model=cfg.judge_model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = message.content[0].text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback: try to extract JSON from the response
        import re
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    raw_score = float(data.get(score_key, 0))
    normalised = min(raw_score / max_score, 1.0) if max_score != 1.0 else raw_score

    return JudgeScore(
        score=normalised,
        verdict=str(data.get("verdict", "unknown")),
        reasoning=str(data.get("reasoning", "")),
        raw=data,
    )
