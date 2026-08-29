"""Redact credentials from coding-session data before it leaves the machine."""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_KNOWN_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"sk-ant-[A-Za-z0-9_-]{16,}|"
    r"sk-proj-[A-Za-z0-9_-]{16,}|"
    r"sk-(?!live_|test_)[A-Za-z0-9_-]{20,}|"
    r"sk_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[opurs]_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{16,}|"
    r"AKIA[A-Z0-9]{16}|"
    r"AIza[A-Za-z0-9_-]{30,}|"
    r"npm_[A-Za-z0-9]{20,}|"
    r"hf_[A-Za-z0-9]{20,}|"
    r"lin_api_[A-Za-z0-9]{20,}|"
    r"phx_[A-Za-z0-9]{20,}"
    r")(?![A-Za-z0-9])"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>\b(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|secret[_-]?(?:access[_-]?)?key|client[_-]?secret|password|passwd)\b"
    r"[\"']?\s*[:=]\s*[\"']?)(?P<secret>(?!\[REDACTED\])[^\s,;\"'\]}]{8,})"
)
_AUTHORIZATION = re.compile(
    r"(?i)(?P<prefix>\b(?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+)"
    r"(?P<secret>[A-Za-z0-9._~+/=-]{12,})"
)
_CREDENTIAL_URL = re.compile(
    r"(?P<prefix>\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)(?P<secret>[^@\s/]+)(?=@)"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
    r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    re.DOTALL,
)


def _redact_named_secret(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}{REDACTED}"


def redact_text(text: str) -> str:
    redacted = _PRIVATE_KEY.sub(REDACTED, text)
    redacted = _KNOWN_TOKEN.sub(REDACTED, redacted)
    redacted = _CREDENTIAL_ASSIGNMENT.sub(_redact_named_secret, redacted)
    redacted = _AUTHORIZATION.sub(_redact_named_secret, redacted)
    return _CREDENTIAL_URL.sub(_redact_named_secret, redacted)


def redact_data(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_data(item) for key, item in value.items()}
    return value


def redact_bytes(content: bytes) -> bytes:
    return redact_text(content.decode("utf-8")).encode("utf-8")
