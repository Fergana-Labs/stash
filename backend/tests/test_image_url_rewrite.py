"""Regex correctness for the 0075 page-image URL rewrite migration."""

import importlib.util
from pathlib import Path

_MIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "0075_rewrite_legacy_r2_image_urls.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0075", _MIG_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_rewrite_swaps_presigned_r2_for_proxy_url():
    mig = _load_migration()
    body = (
        "![cap](https://abc.r2.cloudflarestorage.com/boozle/"
        "24a2d68b-a549-436b-9091-96c0a32acc56/4584cc7269c3/"
        "human-agent-commits-timeline.png?X-Amz-Date=20260518T072209Z&"
        "X-Amz-Expires=3600&X-Amz-Signature=deadbeef)"
    )
    fid = "11111111-2222-3333-4444-555555555555"

    def lookup(storage_key: str) -> str:
        assert (
            storage_key == "24a2d68b-a549-436b-9091-96c0a32acc56/4584cc7269c3/"
            "human-agent-commits-timeline.png"
        )
        return fid

    rewritten = mig._rewrite_body(body, lookup)
    expected = (
        "![cap](/api/v1/workspaces/24a2d68b-a549-436b-9091-96c0a32acc56/" f"files/{fid}/download)"
    )
    assert rewritten == expected


def test_rewrite_url_decodes_filename_for_lookup():
    mig = _load_migration()
    body = (
        "![photo](https://abc.r2.cloudflarestorage.com/boozle/"
        "scope-id/abcdef012345/My%20Vacation%20Photo.png?X-Amz-Signature=x)"
    )

    captured = {}

    def lookup(storage_key: str) -> str:
        captured["key"] = storage_key
        return "file-id"

    mig._rewrite_body(body, lookup)
    assert captured["key"] == "scope-id/abcdef012345/My Vacation Photo.png"


def test_rewrite_leaves_url_alone_when_file_not_found():
    mig = _load_migration()
    body = (
        "![x](https://abc.r2.cloudflarestorage.com/boozle/"
        "scope-id/aaaaaaaaaaaa/missing.png?X-Amz-Signature=y)"
    )

    rewritten = mig._rewrite_body(body, lookup_file_id=lambda _k: None)
    assert rewritten == body


def test_rewrite_ignores_non_r2_urls():
    mig = _load_migration()
    body = (
        "![ok](/api/v1/me/scope/files/abc/download) and ![cdn](https://cdn.example.com/x.png)"
    )
    rewritten = mig._rewrite_body(body, lookup_file_id=lambda _k: "should-not-be-called")
    assert rewritten == body
