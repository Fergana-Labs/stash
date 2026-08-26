"""Cluster the knowledge-map projection and name each cluster from its labels.

The 3D UMAP coords are already neighbor-preserving, so plain k-means on them
splits the cloud into the visible islands. Names are computed in code (no LLM):
tf-idf over the member point labels, so each island is captioned by the terms
that distinguish it from the rest of the map.
"""

import math
import re
from collections import Counter

import numpy as np

MAX_CLUSTERS = 8  # matches the frontend's per-cluster color palette

_STOPWORDS = frozenset(
    """
    a an and are as at be but by for from had has have how i if in into is it
    its me my not of on or our so that the their then there these they this to
    up was we were what when where which who will with you your
    """.split()
)

# UUID/hash fragments: long runs of hex characters carry no meaning in a name.
_HEXISH = re.compile(r"[0-9a-f]{7,}")


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
        top = [term for term, _ in scored[:3]]
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
            tokens.append(token)
    return tokens
