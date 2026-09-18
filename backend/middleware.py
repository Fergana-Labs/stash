"""Shared middleware and rate-limiting configuration."""

import os
import zlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

# Disable rate limiting when running under the test suite (TEST_DATABASE_URL is
# set by conftest.py before any backend module is imported).
_rate_limit_enabled = not bool(os.getenv("TEST_DATABASE_URL"))

limiter = Limiter(key_func=get_remote_address, enabled=_rate_limit_enabled)

# zlib speaks raw deflate by default; the +16 selects the gzip wrapper clients send.
_GZIP_WINDOW = 16 + zlib.MAX_WBITS

# Far above any real body (the largest is a shared session's Full Transcript
# page, under a megabyte) and far below what a gzip bomb aims for.
_MAX_DECOMPRESSED_BODY = 100 * 1024 * 1024


async def _reject(scope, receive, send, status: int, detail: str) -> None:
    await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)


class GzipRequestMiddleware:
    """Decompress request bodies sent with `Content-Encoding: gzip`.

    The Cloudflare WAF fronting Render pattern-matches raw request bodies and
    403s agent-generated shell text as command injection — `stash share` and
    ~1.5% of plugin bash events were eaten by the edge before reaching us
    (measured in plugins commit eae5bdca). We cannot configure that WAF, so
    clients gzip their JSON bodies and the edge has nothing to match. This
    middleware restores the plaintext body before routing sees it.

    Inflating is incremental rather than one `gzip.decompress` of the buffered
    body: compression is an amplifier, so a few hundred kilobytes on the wire
    can inflate to gigabytes of our memory. Streaming lets us stop at the first
    chunk that crosses the ceiling instead of after paying for all of it.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        encoding = next((v for k, v in scope["headers"] if k == b"content-encoding"), b"")
        if encoding.lower() != b"gzip":
            await self.app(scope, receive, send)
            return

        inflater = zlib.decompressobj(_GZIP_WINDOW)
        body = bytearray()
        while True:
            message = await receive()
            # Cap output at one byte past the limit: enough to notice the
            # overflow, never enough to hold the bomb.
            headroom = _MAX_DECOMPRESSED_BODY - len(body) + 1
            try:
                body += inflater.decompress(message.get("body", b""), headroom)
            except zlib.error:
                await _reject(
                    scope, receive, send, 400, "Body does not match Content-Encoding: gzip"
                )
                return
            if len(body) > _MAX_DECOMPRESSED_BODY:
                await _reject(
                    scope, receive, send, 413, "Gzipped body inflates past the size limit"
                )
                return
            if not message.get("more_body", False):
                break

        # A body that stops mid-stream decompresses without error but is
        # missing its tail; routing must never see a half-parsed request.
        if not inflater.eof:
            await _reject(scope, receive, send, 400, "Body does not match Content-Encoding: gzip")
            return

        body = bytes(body)
        scope = dict(scope)
        scope["headers"] = [
            (k, v) for k, v in scope["headers"] if k not in (b"content-encoding", b"content-length")
        ] + [(b"content-length", str(len(body)).encode())]

        replayed = False

        async def receive_decompressed():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, receive_decompressed, send)
