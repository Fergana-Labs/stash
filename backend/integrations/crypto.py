"""Shared encryption for integration credentials and OAuth state."""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet
from fastapi import HTTPException

from ..config import settings

_cached_keys: tuple[str, ...] | None = None
_cached_fernet: MultiFernet | None = None


def _configured_keys() -> tuple[str, ...]:
    raw = settings.INTEGRATIONS_ENCRYPTION_KEY
    if not raw:
        raise HTTPException(status_code=500, detail="INTEGRATIONS_ENCRYPTION_KEY is not set")

    keys = tuple(key.strip() for key in raw.split(",") if key.strip())
    if not keys:
        raise HTTPException(status_code=500, detail="INTEGRATIONS_ENCRYPTION_KEY is not set")
    return keys


def integration_fernet() -> MultiFernet:
    """Return a Fernet keyring; the first key encrypts, all keys can decrypt."""
    global _cached_keys, _cached_fernet

    keys = _configured_keys()
    if _cached_fernet is not None and _cached_keys == keys:
        return _cached_fernet

    fernet = MultiFernet([Fernet(key.encode()) for key in keys])
    _cached_keys = keys
    _cached_fernet = fernet
    return _cached_fernet


def integration_keyring_error() -> str | None:
    if not settings.INTEGRATIONS_ENCRYPTION_KEY:
        return (
            "OAuth integrations are not configured for this server. "
            "Set INTEGRATIONS_ENCRYPTION_KEY to enable them."
        )

    try:
        integration_fernet()
    except ValueError:
        return "INTEGRATIONS_ENCRYPTION_KEY must be one or more valid Fernet keys."
    return None
