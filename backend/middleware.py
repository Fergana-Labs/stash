"""Shared middleware and rate-limiting configuration."""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Disable rate limiting when running under the test suite (TEST_DATABASE_URL is
# set by conftest.py before any backend module is imported).
_rate_limit_enabled = not bool(os.getenv("TEST_DATABASE_URL"))

limiter = Limiter(key_func=get_remote_address, enabled=_rate_limit_enabled)
