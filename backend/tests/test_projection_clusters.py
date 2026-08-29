"""Tests for knowledge-map cluster naming and deterministic k-means.

Cluster names caption the map's islands, so they must surface the terms that
distinguish a cluster — never stopwords, path fragments, or UUID junk, and
never an invented name for a cluster whose labels yield nothing. The concept
naming pass mirrors session-title generation: no API key means no model call,
and malformed model output (after one retry) keeps the keyword names.
"""

import numpy as np
import pytest

from backend.config import settings
from backend.services import projection_clusters
from backend.services.projection_clusters import cluster_points, concept_names, name_clusters


def test_distinguishing_terms_beat_globally_common_ones():
    # "stash" appears in every cluster; each cluster's own topic words don't.
    names = name_clusters(
        [
            ["Stash sessions search", "Stash sessions list view", "Sessions sidebar in stash"],
            ["Stash billing plans", "Billing invoices for stash", "Stash billing webhook"],
        ]
    )
    assert "Sessions" in names[0]
    assert "Billing" in names[1]
    # The shared term must not lead either name.
    assert not names[0].startswith("Stash")
    assert not names[1].startswith("Stash")


def test_names_are_top_terms_title_cased_and_dot_joined():
    names = name_clusters(
        [
            ["sessions search vfs", "sessions search vfs", "sessions search vfs"],
            ["billing invoices", "billing invoices"],
        ]
    )
    assert names[0] == "Search · Sessions · Vfs"
    assert names[1] == "Billing · Invoices"


def test_stopwords_and_junk_never_appear():
    names = name_clusters(
        [
            [
                "Read /Users/henrydowling/projects/stash/backend/main.py",
                "the a0438da674eb37c2b session and the 12345 run",
                "Ran: grep -n embeddings in the backend",
            ]
        ]
    )
    for junk in ["The", "And", "Henrydowling", "A0438da674eb37c2b", "12345"]:
        assert junk not in names[0]
    # Real terms from the labels still make it through.
    assert "Backend" in names[0]


def test_singular_and_plural_never_both_appear():
    # "skill" and "skills" tie for the top terms; the name must fold them.
    names = name_clusters([["skill skills publish", "skill skills publish"]])
    assert names[0] == "Publish · Skill"


def test_number_words_timestamp_fragments_and_generic_verbs_are_dropped():
    names = name_clusters(
        [
            [
                "Ran one memory curation at 2026-08-25T20:01:22Z",
                "Read and edited memory curation notes",
                "Added memory curation across sessions using vfs",
            ]
        ]
    )
    terms = names[0].split(" · ")
    for junk in ["Ran", "One", "20t01", "22z", "Read", "Edited", "Added", "Using", "Across"]:
        assert junk not in terms
    assert "Memory" in terms
    assert "Curation" in terms


def test_cluster_with_no_usable_terms_gets_positional_name():
    names = name_clusters([["sessions search"], ["/a/b/c 123 ab -- of the"]])
    assert names[1] == "Cluster 2"


def test_empty_cluster_list_and_empty_labels():
    assert name_clusters([]) == []
    assert name_clusters([[]]) == ["Cluster 1"]


def test_kmeans_is_deterministic_and_separates_obvious_islands():
    rng = np.random.default_rng(7)
    island_a = rng.normal(loc=(-0.8, -0.8, -0.8), scale=0.05, size=(20, 3))
    island_b = rng.normal(loc=(0.8, 0.8, 0.8), scale=0.05, size=(20, 3))
    coords = np.vstack([island_a, island_b])

    first = cluster_points(coords)
    second = cluster_points(coords)
    assert first == second

    # k may subdivide an island, but no cluster ever straddles both islands.
    assert set(first[:20]).isdisjoint(set(first[20:]))


def test_kmeans_indices_are_compact():
    # 128 points in one tight blob: most of the k seeded centroids collapse,
    # but the returned indices must still be 0..m-1 with no gaps.
    coords = np.full((128, 3), 0.5) + np.linspace(0, 0.001, 128 * 3).reshape(128, 3)
    assignments = cluster_points(coords)
    assert set(assignments) == set(range(max(assignments) + 1))


def test_kmeans_single_point():
    assert cluster_points(np.zeros((1, 3))) == [0]


def _fake_model(monkeypatch, responses: list[str]) -> list[str]:
    """Route _call_fast_model to canned responses; returns the prompts sent."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    prompts: list[str] = []

    async def fake_call(prompt: str) -> str:
        prompts.append(prompt)
        return responses[len(prompts) - 1]

    monkeypatch.setattr(projection_clusters, "_call_fast_model", fake_call)
    return prompts


@pytest.mark.asyncio
async def test_concept_names_replace_keyword_names(monkeypatch):
    prompts = _fake_model(monkeypatch, ['["Memory curation runs", "CLI onboarding work"]'])

    names = await concept_names(
        [["curator run 12", "curator run 13"], ["stash init flow", "cli login"]],
        ["Curator · Runs", "Init · Login"],
    )

    assert names == ["Memory curation runs", "CLI onboarding work"]
    assert len(prompts) == 1
    # One batched call carries every cluster's labels and its keyword hint.
    assert "Curator · Runs" in prompts[0]
    assert "cli login" in prompts[0]


@pytest.mark.asyncio
async def test_concept_names_are_sanitized_and_length_capped(monkeypatch):
    long_name = "An extremely long cluster name that goes on far past forty characters"
    _fake_model(monkeypatch, [f'[" \\"{long_name}\\" "]'])

    names = await concept_names([["a"]], ["Kw"])

    assert len(names[0]) <= 40
    assert not names[0].startswith('"')
    assert names[0] == long_name[:40].strip()


@pytest.mark.asyncio
async def test_concept_names_retry_once_on_malformed_output(monkeypatch):
    # First reply has the wrong shape (one name for two clusters); the retry
    # is well-formed and wins.
    prompts = _fake_model(monkeypatch, ['["only one"]', '["Billing work", "Search work"]'])

    names = await concept_names([["a"], ["b"]], ["Kw A", "Kw B"])

    assert names == ["Billing work", "Search work"]
    assert len(prompts) == 2


@pytest.mark.asyncio
async def test_concept_names_keep_keyword_names_after_two_malformed_replies(monkeypatch):
    prompts = _fake_model(monkeypatch, ["not json at all", '{"still": "wrong"}'])

    names = await concept_names([["a"], ["b"]], ["Kw A", "Kw B"])

    assert names == ["Kw A", "Kw B"]
    assert len(prompts) == 2


@pytest.mark.asyncio
async def test_concept_names_skip_the_model_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    async def must_not_call(prompt: str) -> str:
        raise AssertionError("no API key: the model must not be called")

    monkeypatch.setattr(projection_clusters, "_call_fast_model", must_not_call)

    names = await concept_names([["a"]], ["Kw"])

    assert names == ["Kw"]
