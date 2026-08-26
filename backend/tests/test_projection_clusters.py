"""Tests for knowledge-map cluster naming and deterministic k-means.

Cluster names caption the map's islands, so they must surface the terms that
distinguish a cluster — never stopwords, path fragments, or UUID junk, and
never an invented name for a cluster whose labels yield nothing.
"""

import numpy as np

from backend.services.projection_clusters import cluster_points, name_clusters


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
