"""JSON request bodies must leave the client gzipped.

The Cloudflare WAF fronting the hosted API 403s raw agent shell text as
command injection, which broke `stash share` outright. The client gzips every
JSON body so the edge has nothing to pattern-match; the server decompresses.
"""

from __future__ import annotations

import gzip
import json

import httpx

from cli.client import StashClient

WAF_HOSTILE = '$ TOKEN=$(gcloud auth print-access-token); curl -H "Bearer $TOKEN" x'


def _capture_client(captured: list) -> StashClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    c = StashClient("https://example.test", api_key="k")
    c._http = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))
    return c


def test_json_bodies_are_gzipped():
    captured: list[httpx.Request] = []
    c = _capture_client(captured)

    c._post("/api/v1/me/pages/new", json={"name": "p", "content": WAF_HOSTILE})

    req = captured[0]
    assert req.headers["Content-Encoding"] == "gzip"
    assert req.headers["Content-Type"] == "application/json"
    assert json.loads(gzip.decompress(req.content)) == {
        "name": "p",
        "content": WAF_HOSTILE,
    }


def test_get_requests_are_untouched():
    captured: list[httpx.Request] = []
    c = _capture_client(captured)

    c._get("/api/v1/users/me")

    assert "content-encoding" not in captured[0].headers
