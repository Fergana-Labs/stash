"""Live OTLP/HTTP trace ingestion: agents export spans, Stash keeps traces current.

A BatchSpanProcessor sends one trace's spans across several requests, so raw
spans are stored per (owner, trace id, span id) and every request rebuilds each
affected trace from all of its stored spans through the `otel` adapter. The
rebuilt trace replaces the previous version (same external id = OTel trace id).
"""

import base64
import gzip
import json
from uuid import UUID

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from ...database import get_pool
from . import traces
from .adapters import TraceFormatError, otel_spans_have_messages, parse_traces

PROTOBUF = "application/x-protobuf"
JSON = "application/json"


class UnsupportedContentType(ValueError):
    pass


def _hex_id(value: str) -> str:
    return base64.b64decode(value).hex()


def _hex_span_ids(span: dict) -> None:
    """protobuf's JSON mapping writes bytes as base64; OTLP/JSON uses hex ids."""
    for key in ("traceId", "spanId", "parentSpanId"):
        if key in span:
            span[key] = _hex_id(span[key])
    for link in span.get("links", []):
        for key in ("traceId", "spanId"):
            if key in link:
                link[key] = _hex_id(link[key])


def decode_request(body: bytes, content_type: str, content_encoding: str | None) -> dict:
    """An ExportTraceServiceRequest body as OTLP/JSON (camelCase, hex ids)."""
    media_type = content_type.split(";")[0].strip().lower()
    if media_type not in (PROTOBUF, JSON):
        raise UnsupportedContentType(f"expected {PROTOBUF} or {JSON}, got {media_type!r}")
    if content_encoding not in (None, "identity", "gzip"):
        raise UnsupportedContentType(f"unsupported Content-Encoding {content_encoding!r}")
    if content_encoding == "gzip":
        try:
            body = gzip.decompress(body)
        except (OSError, EOFError) as exc:
            raise TraceFormatError(f"invalid gzip body: {exc}") from exc

    if media_type == JSON:
        try:
            return json.loads(body)
        except ValueError as exc:
            raise TraceFormatError(f"invalid OTLP/JSON body: {exc}") from exc

    try:
        request = ExportTraceServiceRequest.FromString(body)
    except DecodeError as exc:
        raise TraceFormatError(f"invalid OTLP protobuf body: {exc}") from exc
    payload = MessageToDict(request, preserving_proto_field_name=False)
    for span in _spans(payload):
        _hex_span_ids(span)
    return payload


def encode_response(content_type: str) -> tuple[bytes, str]:
    """An empty ExportTraceServiceResponse (full success) in the request's content type."""
    media_type = content_type.split(";")[0].strip().lower()
    if media_type == PROTOBUF:
        return ExportTraceServiceResponse().SerializeToString(), PROTOBUF
    return b"{}", JSON


def _spans(payload: dict) -> list[dict]:
    return [
        span
        for resource_spans in payload.get("resourceSpans", [])
        for scope_spans in resource_spans.get("scopeSpans", [])
        for span in scope_spans.get("spans", [])
    ]


async def ingest(owner_user_id: UUID, payload: dict) -> list[UUID]:
    """Store the payload's spans and rebuild every trace they touch that has LLM messages.

    Returns the ids of the rm_traces rebuilt. One transaction: a batch that
    fails to parse stores nothing.
    """
    spans = _spans(payload)
    for span in spans:
        if not span.get("traceId") or not span.get("spanId"):
            raise TraceFormatError("every span needs a traceId and a spanId")
    otel_trace_ids = sorted({span["traceId"] for span in spans})

    rebuilt = []
    async with get_pool().acquire() as conn, conn.transaction():
        # Concurrent batches of one trace would each rebuild it from a partial
        # span set; serialize them per trace (sorted, so locks can't deadlock).
        for otel_trace_id in otel_trace_ids:
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"rm_otel:{owner_user_id}:{otel_trace_id}",
            )
        await conn.executemany(
            """
            INSERT INTO rm_otel_spans (owner_user_id, otel_trace_id, span_id, span)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (owner_user_id, otel_trace_id, span_id)
            DO UPDATE SET span = EXCLUDED.span, received_at = now()
            """,
            [(owner_user_id, span["traceId"], span["spanId"], span) for span in spans],
        )

        for otel_trace_id in otel_trace_ids:
            stored = await conn.fetch(
                "SELECT span FROM rm_otel_spans WHERE owner_user_id = $1 AND otel_trace_id = $2",
                owner_user_id,
                otel_trace_id,
            )
            trace_spans = [row["span"] for row in stored]
            if not otel_spans_have_messages(trace_spans):
                continue
            data = json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": trace_spans}]}]})
            source_format, parsed = parse_traces(data, "otel")
            rebuilt += await traces.store_traces(conn, owner_user_id, source_format, parsed)
    return rebuilt
