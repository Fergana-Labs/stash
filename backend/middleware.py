"""Shared middleware and rate-limiting configuration."""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Disable rate limiting only when explicitly requested via DISABLE_RATE_LIMITING.
_rate_limit_enabled = os.getenv("DISABLE_RATE_LIMITING", "").lower() not in ("1", "true")

limiter = Limiter(key_func=get_remote_address, enabled=_rate_limit_enabled)
