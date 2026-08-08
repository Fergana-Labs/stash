"""Shared middleware and rate-limiting configuration."""

import gzip
import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

# Disable rate limiting when running under the test suite (TEST_DATABASE_URL is
# set by conftest.py before any backend module is imported).
_rate_limit_enabled = not bool(os.getenv("TEST_DATABASE_URL"))

limiter = Limiter(key_func=get_remote_address, enabled=_rate_limit_enabled)


class GzipRequestMiddleware:
    """Decompress request bodies sent with `Content-Encoding: gzip`.

    The Cloudflare WAF fronting Render pattern-matches raw request bodies and
    403s agent-generated shell text as command injection — `stash share` and
    ~1.5% of plugin bash events were eaten by the edge before reaching us
    (measured in plugins commit eae5bdca). We cannot configure that WAF, so
    clients gzip their JSON bodies and the edge has nothing to match. This
    middleware restores the plaintext body before routing sees it.
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

        chunks = []
        while True:
            message = await receive()
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        try:
            body = gzip.decompress(b"".join(chunks))
        except (OSError, EOFError):
            response = JSONResponse(
                {"detail": "Body does not match Content-Encoding: gzip"},
                status_code=400,
            )
            await response(scope, receive, send)
            return

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
