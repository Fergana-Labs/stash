"""Cluster the knowledge-map projection and name each cluster from its labels.

The 3D UMAP coords are already neighbor-preserving, so plain k-means on them
splits the cloud into the visible islands. Naming is two layers: tf-idf over
the member point labels picks the distinguishing keyword terms, then one
batched fast-model call (`concept_names`) turns each keyword name into a short
noun-phrase concept name. The model pass mirrors session-title generation: no
API key means no call, and output that fails validation keeps the keyword
names.
"""

import json
import math
import re
from collections import Counter

import numpy as np

from ..config import settings

MAX_CLUSTERS = 8  # matches the frontend's per-cluster color palette

CONCEPT_NAME_MAX_CHARS = 40
CONCEPT_LABELS_PER_CLUSTER = 12

_STOPWORDS = frozenset(
    """
    a an and are as at be but by for from had has have how i if in into is it
    its me my not of on or our so that the their then there these they this to
    up was we were what when where which who will with you your
    one two three four five six seven eight nine ten
    ran run running read reads reading edited edit editing edits added add
    adding adds using use used uses across also new
    """.split()
)

# UUID/hash fragments: long runs of hex characters carry no meaning in a name.
_HEXISH = re.compile(r"[0-9a-f]{7,}")

# Timestamp fragments the tokenizer splits ISO datetimes into — digits mixed
# with only t/z, like "20t01" or "08t12z".
_TIMESTAMPISH = re.compile(r"(?=[0-9tz]*[0-9])[0-9tz]+")


def cluster_points(coords: np.ndarray) -> list[int]:
    """Deterministic k-means over the projected 3D coords.

    Centroids seed from evenly-strided points (the input is recency-ordered,
    so the stride spreads seeds across the data) — no randomness, so the same
    projection always clusters the same way. Cluster indices are compacted:
    every returned index is 0..m-1 with at least one member.
    """
    n = len(coords)
    k = max(1, min(MAX_CLUSTERS, round(math.sqrt(n / 2))))
    centroids = coords[[(c * n) // k for c in range(k)]].astype(float)
    assignments = np.zeros(n, dtype=int)

    for _ in range(12):
        distances = ((coords[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        assignments = distances.argmin(axis=1)
        for c in range(k):
            members = coords[assignments == c]
            if len(members) > 0:
                centroids[c] = members.mean(axis=0)

    # Compact away clusters that lost every member.
    occupied = sorted(set(assignments.tolist()))
    remap = {old: new for new, old in enumerate(occupied)}
    return [remap[int(a)] for a in assignments]


def name_clusters(labels_per_cluster: list[list[str]]) -> list[str]:
    """Name each cluster from its member labels: top tf-idf terms, title-cased.

    Term frequency within the cluster is weighted against how many other
    clusters contain the term, so distinguishing terms beat globally common
    ones. A cluster whose labels yield no usable terms is named "Cluster N" —
    nothing is invented.
    """
    counts_per_cluster = [
        Counter(token for label in labels for token in _tokens(label))
        for labels in labels_per_cluster
    ]
    n_clusters = len(counts_per_cluster)
    doc_freq = Counter(term for counts in counts_per_cluster for term in counts)

    names = []
    for i, counts in enumerate(counts_per_cluster):
        scored = sorted(
            counts.items(),
            key=lambda kv: (-_tf_idf(kv[1], doc_freq[kv[0]], n_clusters), kv[0]),
        )
        # Dedupe by naive stem so "Skill · Skills" can't happen.
        top: list[str] = []
        seen_stems: set[str] = set()
        for term, _ in scored:
            if _stem(term) in seen_stems:
                continue
            seen_stems.add(_stem(term))
            top.append(term)
            if len(top) == 3:
                break
        if not top:
            names.append(f"Cluster {i + 1}")
        else:
            names.append(" · ".join(term.capitalize() for term in top))
    return names


def _tf_idf(term_count: int, cluster_doc_freq: int, n_clusters: int) -> float:
    # Smoothed idf (never zero), so single-cluster maps still rank by frequency.
    return term_count * (math.log((1 + n_clusters) / (1 + cluster_doc_freq)) + 1)


def _tokens(label: str) -> list[str]:
    tokens = []
    for word in label.lower().split():
        if "/" in word:  # file paths are noise, not meaning
            continue
        for token in re.split(r"[^a-z0-9]+", word):
            if len(token) < 3:
                continue
            if token in _STOPWORDS:
                continue
            if token.isdigit():
                continue
            if _HEXISH.fullmatch(token):
                continue
            if _TIMESTAMPISH.fullmatch(token):
                continue
            tokens.append(token)
    return tokens


def _stem(token: str) -> str:
    """Naive plural stem, just enough to fold "skills" into "skill"."""
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


async def concept_names(labels_per_cluster: list[list[str]], keyword_names: list[str]) -> list[str]:
    """Concept names for the clusters via one batched fast-model call.

    Each cluster's top member labels (plus its keyword name as a hint) go to
    the fast model, which returns a JSON array of 2-4 word noun-phrase names.
    Mirrors session-title generation: without an API key the call is skipped
    and the keyword names stand; malformed output is retried once, then the
    keyword names stand.
    """
    if not labels_per_cluster:
        return keyword_names
    if not settings.ANTHROPIC_API_KEY:
        return keyword_names

    prompt = _concept_prompt(labels_per_cluster, keyword_names)
    for _ in range(2):
        text = await _call_fast_model(prompt)
        names = _parse_concept_names(text, len(labels_per_cluster))
        if names is not None:
            return names
    return keyword_names


async def _call_fast_model(prompt: str) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=settings.ANTHROPIC_FAST_MODEL,
        max_tokens=400,
        system=(
            "You name clusters of related work items on a knowledge map. For "
            "each numbered cluster you are given member labels and a keyword "
            "hint. Reply with ONLY a JSON array of strings — one name per "
            "cluster, in order. Each name is a concrete noun phrase of 2 to 4 "
            'words naming the shared concept (e.g. "Memory curation runs", '
            '"CLI onboarding work"). No numbering, no explanations.'
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return "\n".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )


def _concept_prompt(labels_per_cluster: list[list[str]], keyword_names: list[str]) -> str:
    lines = []
    for i, labels in enumerate(labels_per_cluster):
        lines.append(f"Cluster {i + 1} (keywords: {keyword_names[i]}):")
        for label in labels[:CONCEPT_LABELS_PER_CLUSTER]:
            lines.append(f"- {label[:120]}")
    return "\n".join(lines)


def _parse_concept_names(text: str, n_clusters: int) -> list[str] | None:
    """The model's names, sanitized — or None when the output is malformed."""
    raw = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or len(parsed) != n_clusters:
        return None
    if not all(isinstance(name, str) for name in parsed):
        return None
    names = [_sanitize_concept_name(name) for name in parsed]
    if not all(names):
        return None
    return names


def _sanitize_concept_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip("`\"' ")
    return cleaned[:CONCEPT_NAME_MAX_CHARS].strip()
