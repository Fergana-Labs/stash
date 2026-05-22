"""Builder-level tests that bypass the real Aspose service.

We replace the HTTP transport with `httpx.MockTransport` and assert
the request payloads match the SlideSpec — no network, no .NET, runs on
macOS in milliseconds. The actual Aspose-side rendering quality is
validated by the Render deployment + diff harness.
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field

import httpx

from backend.exports.native.aspose_builder import build_pptx_via_aspose
from backend.exports.native.image_fetch import ImageFetcher
from backend.exports.native.spec import (
    BBox,
    Paragraph,
    ShapeSpec,
    SlideSpec,
    TextRun,
)


@dataclass
class _RecordedRequest:
    method: str
    path: str
    body: dict | None = None


@dataclass
class _Recorder:
    requests: list[_RecordedRequest] = field(default_factory=list)
    session_id: str = "sess-test"
    next_slide_index: int = 0
    next_shape_index: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = None
        if request.content:
            try:
                body = json.loads(request.content)
            except Exception:
                body = None
        self.requests.append(_RecordedRequest(request.method, request.url.path, body))

        if request.method == "POST" and request.url.path == "/sessions":
            return httpx.Response(200, json={"session_id": self.session_id})
        if request.method == "POST" and request.url.path.endswith("/slides") \
                and not request.url.path.endswith("/slides/0/text"):
            # /sessions/{sid}/slides — add a blank slide
            if request.url.path == f"/sessions/{self.session_id}/slides":
                idx = self.next_slide_index
                self.next_slide_index += 1
                return httpx.Response(200, json={"slide_index": idx})
        if request.method == "POST" and any(
            request.url.path.endswith(suffix)
            for suffix in ("/text", "/image", "/raster", "/table")
        ):
            idx = self.next_shape_index
            self.next_shape_index += 1
            return httpx.Response(200, json={"shape_index": idx})
        if request.method == "GET" and request.url.path.endswith("/pptx"):
            return httpx.Response(
                200,
                content=b"PK\x03\x04stub-pptx-bytes",
                headers={"content-type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
            )
        if request.method == "DELETE" and request.url.path.startswith("/sessions/"):
            return httpx.Response(200, json={"ok": True})

        return httpx.Response(404, json={"detail": "unhandled in mock"})


class _StubFetcher(ImageFetcher):
    """Returns deterministic bytes for any URL, so image shapes hit the
    /image endpoint without touching the network."""

    async def fetch(self, src):  # type: ignore[override]
        if not src:
            return None
        return b"fake-png-bytes-for-" + src.encode()


def _build(specs: list[SlideSpec]) -> tuple[bytes, _Recorder]:
    recorder = _Recorder()
    transport = httpx.MockTransport(recorder.handler)

    async def _run() -> bytes:
        async with httpx.AsyncClient(
            base_url="http://aspose.test", transport=transport, timeout=5.0,
        ) as client:
            return await build_pptx_via_aspose(
                specs,
                html="<html><body></body></html>",
                base_url="http://aspose.test",
                image_fetcher=_StubFetcher(),
                http_client=client,
            )

    pptx = asyncio.run(_run())
    return pptx, recorder


def test_session_create_and_teardown_around_one_slide():
    specs = [SlideSpec(index=0, bg_color="#0F172A", shapes=[])]
    pptx, recorder = _build(specs)

    assert pptx.startswith(b"PK"), "service responded with PPTX bytes"

    paths = [(r.method, r.path) for r in recorder.requests]
    assert ("POST", "/sessions") in paths
    assert ("POST", "/sessions/sess-test/slides") in paths
    assert ("GET", "/sessions/sess-test/pptx") in paths
    assert ("DELETE", "/sessions/sess-test") in paths
    # DELETE always comes last (teardown in finally).
    assert paths[-1] == ("DELETE", "/sessions/sess-test")


def test_text_shape_payload_carries_paragraphs_and_padding():
    spec = SlideSpec(
        index=0,
        shapes=[
            ShapeSpec(
                kind="text",
                bbox=BBox(x=64, y=64, w=1792, h=120),
                paragraphs=[
                    Paragraph(
                        runs=[
                            TextRun(
                                text="Hello",
                                bold=True,
                                font_size_px=96,
                                color="#FFFFFF",
                                font_family="Inter",
                            ),
                        ],
                        align="center",
                        line_height=1.1,
                    ),
                ],
                bg_color="#1A73E8",
                padding_px=(8.0, 16.0, 8.0, 16.0),
            ),
        ],
    )
    _, recorder = _build([spec])

    text_calls = [r for r in recorder.requests if r.path.endswith("/text")]
    assert len(text_calls) == 1
    body = text_calls[0].body
    assert body["bbox"] == {"x": 64, "y": 64, "w": 1792, "h": 120}
    assert body["bg_color"] == "#1A73E8"
    assert body["padding_px"] == [8.0, 16.0, 8.0, 16.0]
    assert body["paragraphs"][0]["align"] == "center"
    run = body["paragraphs"][0]["runs"][0]
    assert run["text"] == "Hello"
    assert run["bold"] is True
    assert run["color"] == "#FFFFFF"
    assert run["font_family"] == "Inter"


def test_image_shape_resolves_via_fetcher_and_base64_encodes():
    spec = SlideSpec(
        index=0,
        shapes=[
            ShapeSpec(
                kind="image",
                bbox=BBox(x=10, y=20, w=300, h=200),
                src="https://example.com/pic.png",
            ),
        ],
    )
    _, recorder = _build([spec])
    image_calls = [r for r in recorder.requests if r.path.endswith("/image")]
    assert len(image_calls) == 1
    body = image_calls[0].body
    assert body["bbox"] == {"x": 10, "y": 20, "w": 300, "h": 200}
    decoded = base64.b64decode(body["image_base64"])
    assert decoded == b"fake-png-bytes-for-https://example.com/pic.png"


def test_image_shape_with_no_src_skipped_entirely():
    spec = SlideSpec(
        index=0,
        shapes=[ShapeSpec(kind="image", bbox=BBox(x=0, y=0, w=10, h=10), src=None)],
    )
    _, recorder = _build([spec])
    assert not any(r.path.endswith("/image") for r in recorder.requests)


def test_shapes_posted_in_z_order_low_to_high():
    spec = SlideSpec(
        index=0,
        shapes=[
            ShapeSpec(kind="text", bbox=BBox(0, 0, 10, 10), z=5,
                      paragraphs=[Paragraph(runs=[TextRun(text="top")])]),
            ShapeSpec(kind="text", bbox=BBox(0, 0, 10, 10), z=1,
                      paragraphs=[Paragraph(runs=[TextRun(text="bottom")])]),
        ],
    )
    _, recorder = _build([spec])
    text_calls = [r for r in recorder.requests if r.path.endswith("/text")]
    assert text_calls[0].body["paragraphs"][0]["runs"][0]["text"] == "bottom"
    assert text_calls[1].body["paragraphs"][0]["runs"][0]["text"] == "top"


def test_multi_slide_call_sequence_creates_each_slide_independently():
    specs = [
        SlideSpec(index=0, bg_color="#000000", shapes=[]),
        SlideSpec(index=1, bg_color="#FFFFFF", shapes=[]),
    ]
    _, recorder = _build(specs)
    slide_calls = [r for r in recorder.requests if r.path == "/sessions/sess-test/slides"]
    assert len(slide_calls) == 2
    assert slide_calls[0].body["bg_color"] == "#000000"
    assert slide_calls[1].body["bg_color"] == "#FFFFFF"


def test_teardown_runs_even_when_pptx_fetch_fails():
    spec = SlideSpec(index=0, shapes=[])

    requests: list[_RecordedRequest] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        requests.append(_RecordedRequest(request.method, request.url.path, body))
        if request.method == "POST" and request.url.path == "/sessions":
            return httpx.Response(200, json={"session_id": "sess-x"})
        if request.method == "POST" and request.url.path == "/sessions/sess-x/slides":
            return httpx.Response(200, json={"slide_index": 0})
        if request.method == "GET" and request.url.path == "/sessions/sess-x/pptx":
            return httpx.Response(500, json={"detail": "boom"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async def _run():
        async with httpx.AsyncClient(
            base_url="http://aspose.test", transport=transport, timeout=5.0,
        ) as client:
            try:
                await build_pptx_via_aspose(
                    [spec], html="", base_url="http://aspose.test",
                    image_fetcher=_StubFetcher(), http_client=client,
                )
            except httpx.HTTPStatusError:
                pass

    asyncio.run(_run())
    assert any(r.method == "DELETE" and r.path == "/sessions/sess-x" for r in requests)
