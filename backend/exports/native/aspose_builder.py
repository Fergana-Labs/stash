"""list[SlideSpec] → PPTX bytes via the remote `aspose-pptx` service.

Peer of `pptx_builder.build_pptx`. Same SlideSpec input, same `(specs,
html)` signature. The difference is the actual shape construction
happens out-of-process inside an Aspose.Slides session over HTTP because
Aspose's Python bindings can't run on macOS.

Wire format mirrors `backend/exports/native/spec.py` 1:1 — see
`powerpoint-mcp/src/models.py` on the service side.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import asdict

import httpx

from ..constants import SLIDE_HEIGHT_PX, SLIDE_WIDTH_PX
from .hybrid_raster import rasterize_targets
from .image_fetch import ImageFetcher
from .spec import BBox, ShapeSpec, SlideSpec

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 120.0


async def build_pptx_via_aspose(
    specs: list[SlideSpec],
    html: str,
    *,
    base_url: str,
    token: str | None = None,
    image_fetcher: ImageFetcher | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """Build a PPTX by driving the remote Aspose service per-shape.

    Always tears the session down — even on failure — so a long-running
    sandbox process doesn't accrete sessions in the service's LRU.
    """
    fetcher = image_fetcher or ImageFetcher()

    raster_targets: list[tuple[int, str]] = []
    for spec in specs:
        if spec.bg_raster_selector:
            raster_targets.append((spec.index, spec.bg_raster_selector))
        for sh in _walk_shapes(spec.shapes):
            if sh.kind == "raster" and sh.raster_selector:
                raster_targets.append((spec.index, sh.raster_selector))
    rasters = await rasterize_targets(html, raster_targets)

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    client = http_client or httpx.AsyncClient(
        base_url=base_url, timeout=_DEFAULT_TIMEOUT_S, headers=headers,
    )
    owns_client = http_client is None

    session_id: str | None = None
    try:
        resp = await client.post(
            "/sessions",
            json={"slide_width_px": float(SLIDE_WIDTH_PX), "slide_height_px": float(SLIDE_HEIGHT_PX)},
        )
        resp.raise_for_status()
        session_id = resp.json()["session_id"]

        for spec in specs:
            await _post_slide(client, session_id, spec, rasters, fetcher)

        pptx_resp = await client.get(f"/sessions/{session_id}/pptx")
        pptx_resp.raise_for_status()
        return pptx_resp.content
    finally:
        if session_id:
            try:
                await client.delete(f"/sessions/{session_id}")
            except Exception:
                logger.exception("failed to delete aspose session %s", session_id)
        if owns_client:
            await client.aclose()


async def _post_slide(
    client: httpx.AsyncClient,
    session_id: str,
    spec: SlideSpec,
    rasters: dict[tuple[int, str], bytes],
    fetcher: ImageFetcher,
) -> None:
    slide_body: dict = {"bg_color": spec.bg_color}
    if spec.bg_gradient and spec.bg_gradient.stops:
        slide_body["bg_gradient"] = asdict(spec.bg_gradient)

    resp = await client.post(f"/sessions/{session_id}/slides", json=slide_body)
    resp.raise_for_status()
    slide_index = resp.json()["slide_index"]

    # Background raster is now a last-resort fallback for bgs we couldn't
    # parse as a gradient (image url, multi-layer, conic, etc).
    if spec.bg_raster_selector and not spec.bg_gradient:
        png = rasters.get((spec.index, spec.bg_raster_selector))
        if png:
            await _post_raster(
                client, session_id, slide_index,
                bbox=BBox(x=0, y=0, w=SLIDE_WIDTH_PX, h=SLIDE_HEIGHT_PX),
                png=png,
            )

    for sh in sorted(spec.shapes, key=lambda s: s.z):
        await _post_shape(client, session_id, slide_index, sh, spec.index, rasters, fetcher)


async def _post_shape(
    client: httpx.AsyncClient,
    session_id: str,
    slide_index: int,
    sh: ShapeSpec,
    src_slide_idx: int,
    rasters: dict[tuple[int, str], bytes],
    fetcher: ImageFetcher,
) -> None:
    if sh.kind == "svg" and sh.svg:
        await _post_svg(client, session_id, slide_index, sh)
        return

    if sh.kind == "chart" and sh.chart:
        await _post_chart(client, session_id, slide_index, sh)
        return

    if sh.kind == "raster":
        png = rasters.get((src_slide_idx, sh.raster_selector or ""))
        if png:
            await _post_raster(client, session_id, slide_index, bbox=sh.bbox, png=png)
        return

    if sh.kind == "image":
        data = await fetcher.fetch(sh.src) if sh.src else None
        if not data:
            return
        await _post_image(client, session_id, slide_index, bbox=sh.bbox, data=data)
        return

    if sh.kind == "table":
        await _post_table(client, session_id, slide_index, sh)
        return

    await _post_text(client, session_id, slide_index, sh)


async def _post_svg(
    client: httpx.AsyncClient, session_id: str, slide_index: int, sh: ShapeSpec,
) -> None:
    resp = await client.post(
        f"/sessions/{session_id}/slides/{slide_index}/svg",
        json={"bbox": asdict(sh.bbox), "svg": sh.svg},
    )
    resp.raise_for_status()


async def _post_chart(
    client: httpx.AsyncClient, session_id: str, slide_index: int, sh: ShapeSpec,
) -> None:
    chart = sh.chart
    if chart is None:
        return
    resp = await client.post(
        f"/sessions/{session_id}/slides/{slide_index}/chart",
        json={
            "bbox": asdict(sh.bbox),
            "type": chart.type,
            "labels": chart.labels,
            "datasets": [asdict(d) for d in chart.datasets],
            "title": chart.title,
        },
    )
    resp.raise_for_status()


async def _post_text(
    client: httpx.AsyncClient, session_id: str, slide_index: int, sh: ShapeSpec,
) -> None:
    resp = await client.post(
        f"/sessions/{session_id}/slides/{slide_index}/text",
        json={
            "bbox": asdict(sh.bbox),
            "paragraphs": [asdict(p) for p in sh.paragraphs],
            "bg_color": sh.bg_color,
            "padding_px": list(sh.padding_px),
        },
    )
    resp.raise_for_status()


async def _post_raster(
    client: httpx.AsyncClient, session_id: str, slide_index: int,
    *, bbox: BBox, png: bytes,
) -> None:
    resp = await client.post(
        f"/sessions/{session_id}/slides/{slide_index}/raster",
        json={
            "bbox": asdict(bbox),
            "image_base64": base64.b64encode(png).decode("ascii"),
        },
    )
    resp.raise_for_status()


async def _post_image(
    client: httpx.AsyncClient, session_id: str, slide_index: int,
    *, bbox: BBox, data: bytes,
) -> None:
    resp = await client.post(
        f"/sessions/{session_id}/slides/{slide_index}/image",
        json={
            "bbox": asdict(bbox),
            "image_base64": base64.b64encode(data).decode("ascii"),
        },
    )
    resp.raise_for_status()


async def _post_table(
    client: httpx.AsyncClient, session_id: str, slide_index: int, sh: ShapeSpec,
) -> None:
    cells_payload: list[list[dict]] = []
    for row in sh.cells:
        row_payload: list[dict] = []
        for cell in row:
            # Each table cell carries its own paragraphs in the spec; we
            # only pass the first paragraph through. Multi-paragraph
            # cells degrade to their leading paragraph — the sandbox
            # doesn't emit those today.
            first = cell.paragraphs[0] if cell.paragraphs else None
            if first is None:
                row_payload.append({"runs": [], "align": "left", "line_height": 1.2})
            else:
                row_payload.append(asdict(first))
        cells_payload.append(row_payload)

    resp = await client.post(
        f"/sessions/{session_id}/slides/{slide_index}/table",
        json={"bbox": asdict(sh.bbox), "cells": cells_payload},
    )
    resp.raise_for_status()


def _walk_shapes(shapes: list[ShapeSpec]):
    for s in shapes:
        yield s
        for row in s.cells:
            for cell in row:
                yield from _walk_shapes([cell])
