"""Storage service: S3-compatible async file storage.

Supports AWS S3, MinIO, Cloudflare R2, and other S3-compatible services.
Configured via environment variables.
"""

import logging
import os
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_PUBLIC_URL = os.getenv("S3_PUBLIC_URL", "")  # Optional: public base URL for direct access

_client: httpx.AsyncClient | None = None


def is_configured() -> bool:
    return bool(S3_BUCKET and S3_ENDPOINT and S3_ACCESS_KEY and S3_SECRET_KEY)


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


def _storage_key(workspace_id: str | None, filename: str) -> str:
    """Generate a unique storage key: {workspace_or_personal}/{uuid}/{filename}."""
    prefix = str(workspace_id) if workspace_id else "personal"
    return f"{prefix}/{uuid4().hex[:12]}/{filename}"


async def upload_file(
    workspace_id: str | None,
    filename: str,
    content: bytes,
    content_type: str,
) -> str:
    """Upload a file to S3. Returns the storage key."""
    if not is_configured():
        raise RuntimeError("S3 storage is not configured")

    key = _storage_key(workspace_id, filename)

    # Use S3 PUT Object with presigned-style direct upload
    # For simplicity, use the S3 REST API directly via httpx
    import hashlib
    import hmac
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    date_stamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")

    # Canonical request components
    host = S3_ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
    scheme = "https" if S3_ENDPOINT.startswith("https") else "http"
    uri = f"/{S3_BUCKET}/{key}"

    payload_hash = hashlib.sha256(content).hexdigest()

    headers_to_sign = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "content-type": content_type,
    }
    signed_headers = ";".join(sorted(headers_to_sign.keys()))
    canonical_headers = "".join(
        f"{k}:{v}\n" for k, v in sorted(headers_to_sign.items())
    )

    canonical_request = (
        f"PUT\n{uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    credential_scope = f"{date_stamp}/{S3_REGION}/s3/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode()).hexdigest()
    )

    def _sign(key_bytes: bytes, msg: str) -> bytes:
        return hmac.new(key_bytes, msg.encode(), hashlib.sha256).digest()

    signing_key = _sign(
        _sign(
            _sign(
                _sign(f"AWS4{S3_SECRET_KEY}".encode(), date_stamp),
                S3_REGION,
            ),
            "s3",
        ),
        "aws4_request",
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode(), hashlib.sha256
    ).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={S3_ACCESS_KEY}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    client = _get_client()
    resp = await client.put(
        f"{scheme}://{host}{uri}",
        content=content,
        headers={
            "Authorization": auth_header,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            "Content-Type": content_type,
        },
    )
    resp.raise_for_status()
    return key


async def get_file_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned GET URL for a storage key."""
    if S3_PUBLIC_URL:
        return f"{S3_PUBLIC_URL.rstrip('/')}/{key}"

    if not is_configured():
        raise RuntimeError("S3 storage is not configured")

    import hashlib
    import hmac
    from datetime import datetime, timezone
    from urllib.parse import quote

    now = datetime.now(timezone.utc)
    date_stamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")

    host = S3_ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
    scheme = "https" if S3_ENDPOINT.startswith("https") else "http"
    uri = f"/{S3_BUCKET}/{key}"

    credential_scope = f"{date_stamp}/{S3_REGION}/s3/aws4_request"
    credential = f"{S3_ACCESS_KEY}/{credential_scope}"

    query_params = (
        f"X-Amz-Algorithm=AWS4-HMAC-SHA256"
        f"&X-Amz-Credential={quote(credential, safe='')}"
        f"&X-Amz-Date={amz_date}"
        f"&X-Amz-Expires={expires_in}"
        f"&X-Amz-SignedHeaders=host"
    )

    canonical_request = (
        f"GET\n{uri}\n{query_params}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    )

    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode()).hexdigest()
    )

    def _sign(key_bytes: bytes, msg: str) -> bytes:
        return hmac.new(key_bytes, msg.encode(), hashlib.sha256).digest()

    signing_key = _sign(
        _sign(
            _sign(
                _sign(f"AWS4{S3_SECRET_KEY}".encode(), date_stamp),
                S3_REGION,
            ),
            "s3",
        ),
        "aws4_request",
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode(), hashlib.sha256
    ).hexdigest()

    return f"{scheme}://{host}{uri}?{query_params}&X-Amz-Signature={signature}"


async def delete_file(key: str) -> None:
    """Delete a file from S3."""
    if not is_configured():
        raise RuntimeError("S3 storage is not configured")

    import hashlib
    import hmac
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    date_stamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")

    host = S3_ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
    scheme = "https" if S3_ENDPOINT.startswith("https") else "http"
    uri = f"/{S3_BUCKET}/{key}"

    payload_hash = hashlib.sha256(b"").hexdigest()

    headers_to_sign = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    signed_headers = ";".join(sorted(headers_to_sign.keys()))
    canonical_headers = "".join(
        f"{k}:{v}\n" for k, v in sorted(headers_to_sign.items())
    )

    canonical_request = (
        f"DELETE\n{uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    credential_scope = f"{date_stamp}/{S3_REGION}/s3/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode()).hexdigest()
    )

    def _sign(key_bytes: bytes, msg: str) -> bytes:
        return hmac.new(key_bytes, msg.encode(), hashlib.sha256).digest()

    signing_key = _sign(
        _sign(
            _sign(
                _sign(f"AWS4{S3_SECRET_KEY}".encode(), date_stamp),
                S3_REGION,
            ),
            "s3",
        ),
        "aws4_request",
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode(), hashlib.sha256
    ).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={S3_ACCESS_KEY}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    client = _get_client()
    resp = await client.request(
        "DELETE",
        f"{scheme}://{host}{uri}",
        headers={
            "Authorization": auth_header,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        },
    )
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
