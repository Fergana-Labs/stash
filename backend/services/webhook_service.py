"""Webhook service: per-workspace webhooks with event filtering."""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

import httpx

from ..database import get_pool

logger = logging.getLogger("boozle")

# Private / reserved IP ranges that must not be targeted by webhooks (SSRF guard)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_webhook_url(url: str) -> None:
    """Raise ValueError if url is not a safe HTTPS target."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use HTTPS")
    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL must have a valid hostname")

    # Resolve hostname to IP(s) and block private ranges
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve webhook hostname: {exc}") from exc

    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                raise ValueError(
                    f"Webhook URL resolves to a private/reserved address ({ip}) which is not allowed"
                )


async def create_webhook(
    workspace_id: UUID, user_id: UUID, url: str,
    secret: str | None = None, event_filter: list[str] | None = None,
) -> dict:
    _validate_webhook_url(url)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest() if secret else None
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO webhooks (workspace_id, user_id, url, secret_hash, event_filter)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (workspace_id, user_id) DO UPDATE
             SET url = EXCLUDED.url,
                 secret_hash = EXCLUDED.secret_hash,
                 event_filter = EXCLUDED.event_filter,
                 is_active = true,
                 updated_at = now()
           RETURNING id, workspace_id, user_id, url, secret_hash, event_filter, is_active, created_at, updated_at""",
        workspace_id, user_id, url, secret_hash, event_filter or [],
    )
    return _row_to_dict(row)


async def get_webhook(workspace_id: UUID, user_id: UUID) -> dict | None:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, workspace_id, user_id, url, secret_hash, event_filter, is_active, created_at, updated_at "
        "FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
        workspace_id, user_id,
    )
    return _row_to_dict(row) if row else None


async def update_webhook(
    workspace_id: UUID, user_id: UUID,
    url: str | None = None, secret: str | None = None,
    event_filter: list[str] | None = None, is_active: bool | None = None,
) -> dict | None:
    if url is not None:
        _validate_webhook_url(url)

    sets, args, idx = [], [], 1
    if url is not None:
        sets.append(f"url = ${idx}")
        args.append(url)
        idx += 1
    if secret is not None:
        sets.append(f"secret_hash = ${idx}")
        args.append(hashlib.sha256(secret.encode()).hexdigest())
        idx += 1
    if event_filter is not None:
        sets.append(f"event_filter = ${idx}")
        args.append(event_filter)
        idx += 1
    if is_active is not None:
        sets.append(f"is_active = ${idx}")
        args.append(is_active)
        idx += 1
    if not sets:
        return await get_webhook(workspace_id, user_id)
    sets.append("updated_at = now()")
    args.extend([workspace_id, user_id])
    pool = get_pool()
    row = await pool.fetchrow(
        f"UPDATE webhooks SET {', '.join(sets)} "
        f"WHERE workspace_id = ${idx} AND user_id = ${idx + 1} "
        "RETURNING id, workspace_id, user_id, url, secret_hash, event_filter, is_active, created_at, updated_at",
        *args,
    )
    return _row_to_dict(row) if row else None


async def delete_webhook(workspace_id: UUID, user_id: UUID) -> bool:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM webhooks WHERE workspace_id = $1 AND user_id = $2",
        workspace_id, user_id,
    )
    return result == "DELETE 1"


async def get_webhooks_for_workspace(workspace_id: UUID) -> list[dict]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT id, user_id, url, secret_hash, event_filter "
        "FROM webhooks WHERE workspace_id = $1 AND is_active = true",
        workspace_id,
    )
    return [dict(r) for r in rows]


async def _deliver_once(
    http: httpx.AsyncClient, url: str, secret_hash: str | None, payload_str: str,
) -> bool:
    """Attempt a single HTTP delivery. Returns True on success (2xx/3xx).

    Signing scheme: X-Webhook-Signature = HMAC-SHA256(key=SHA256(secret), body).
    Consumers must compute SHA256 of their stored secret to derive the HMAC key.
    """
    headers = {"Content-Type": "application/json"}
    if secret_hash:
        sig = hmac.new(
            secret_hash.encode(), payload_str.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={sig}"
    try:
        resp = await http.post(url, content=payload_str, headers=headers)
        return resp.status_code < 400
    except Exception:
        return False


async def dispatch_webhooks(
    workspace_id: UUID, event_type: str, event: dict,
    sender_id: UUID | None = None,
):
    """Enqueue webhook deliveries for a workspace event (DB-backed, survives restarts)."""
    pool = get_pool()
    try:
        webhooks = await get_webhooks_for_workspace(workspace_id)
    except Exception:
        logger.warning("Failed to fetch webhooks for workspace %s", workspace_id, exc_info=True)
        return

    envelope = {
        "event": event_type,
        "workspace_id": str(workspace_id),
        "data": event,
    }

    for wh in webhooks:
        if sender_id and wh["user_id"] == sender_id:
            continue
        ef = wh.get("event_filter", [])
        if ef and event_type not in ef:
            continue
        try:
            # Pass the dict directly — the asyncpg jsonb codec handles serialization
            serialisable_envelope = json.loads(json.dumps(envelope, default=str))
            await pool.execute(
                "INSERT INTO webhook_deliveries (webhook_id, event_type, payload) VALUES ($1, $2, $3)",
                wh["id"], event_type, serialisable_envelope,
            )
        except Exception:
            logger.warning("Failed to enqueue webhook delivery for %s", wh["id"], exc_info=True)


_MAX_DELIVERY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = [0, 60, 300]  # immediate, 1 min, 5 min


_DELIVERY_LOCK_ID = 0x600D_BEEF  # arbitrary fixed advisory-lock key


async def process_pending_deliveries() -> None:
    """Pick up pending webhook_deliveries and attempt HTTP delivery with backoff.

    Uses a Postgres advisory lock to serialise across workers so the same
    delivery is never attempted by two processes simultaneously.
    """
    pool = get_pool()

    # Hold a dedicated connection for the advisory lock's lifetime.
    # pg_try_advisory_lock is session-level: the lock persists until we
    # explicitly release it or the connection closes.
    conn = await pool.acquire()
    try:
        acquired = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", _DELIVERY_LOCK_ID
        )
        if not acquired:
            return  # another worker is already delivering

        now = datetime.now(timezone.utc)
        rows = await pool.fetch(
            "SELECT wd.id, wd.webhook_id, wd.event_type, wd.payload, wd.attempts, "
            "       w.url, w.secret_hash "
            "FROM webhook_deliveries wd "
            "JOIN webhooks w ON w.id = wd.webhook_id "
            "WHERE wd.status = 'pending' AND wd.next_retry_at <= $1 "
            "ORDER BY wd.next_retry_at ASC LIMIT 50",
            now,
        )
        if not rows:
            return

        async with httpx.AsyncClient(timeout=10) as http:
            for row in rows:
                delivery_id = row["id"]
                attempts = row["attempts"] + 1
                payload = row["payload"]
                payload_str = json.dumps(payload, default=str) if not isinstance(payload, str) else payload
                success = await _deliver_once(http, row["url"], row["secret_hash"], payload_str)

                if success:
                    await pool.execute(
                        "UPDATE webhook_deliveries SET status = 'delivered', attempts = $1, delivered_at = now() "
                        "WHERE id = $2",
                        attempts, delivery_id,
                    )
                elif attempts >= _MAX_DELIVERY_ATTEMPTS:
                    await pool.execute(
                        "UPDATE webhook_deliveries SET status = 'failed', attempts = $1 WHERE id = $2",
                        attempts, delivery_id,
                    )
                    logger.warning(
                        "Webhook delivery permanently failed after %d attempts (id=%s)",
                        attempts, delivery_id,
                    )
                else:
                    backoff = _RETRY_BACKOFF_SECONDS[min(attempts, len(_RETRY_BACKOFF_SECONDS) - 1)]
                    next_retry = now + timedelta(seconds=backoff)
                    await pool.execute(
                        "UPDATE webhook_deliveries SET attempts = $1, next_retry_at = $2 WHERE id = $3",
                        attempts, next_retry, delivery_id,
                    )
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", _DELIVERY_LOCK_ID)
        except Exception:
            pass  # lock auto-releases when the connection closes
        await pool.release(conn)


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["has_secret"] = d.pop("secret_hash", None) is not None
    return d
