"""Tests for webhook SSRF protection, secret hashing, and delivery logic."""

import socket
from unittest.mock import patch

import pytest

from backend.services.webhook_service import _validate_webhook_url


def _fake_getaddrinfo_public(host, port, *args, **kwargs):
    """Return a fake addrinfo resolving to a public IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]


class TestSSRFValidation:
    def test_rejects_http(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_webhook_url("http://example.com/hook")

    def test_rejects_loopback(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://127.0.0.1/hook")

    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://localhost/hook")

    def test_rejects_private_10(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://10.0.0.1/hook")

    def test_rejects_private_192_168(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://192.168.1.1/hook")

    def test_rejects_link_local(self):
        with pytest.raises(ValueError, match="private"):
            _validate_webhook_url("https://169.254.169.254/hook")

    def test_rejects_no_scheme(self):
        with pytest.raises(ValueError):
            _validate_webhook_url("example.com/hook")

    def test_accepts_valid_https(self):
        with patch("socket.getaddrinfo", _fake_getaddrinfo_public):
            _validate_webhook_url("https://hooks.example.com/post")


class TestSecretHashing:
    """Ensure webhook secrets are stored as hashes, not plaintext."""

    @pytest.mark.asyncio
    async def test_secret_is_hashed(self, pool):
        import hashlib
        import uuid

        # Insert a user and workspace directly
        api_key_hash = "hash_" + uuid.uuid4().hex
        user = await pool.fetchrow(
            "INSERT INTO users (name, type, api_key_hash) VALUES ($1, 'human', $2) RETURNING id",
            f"whtest_{uuid.uuid4().hex[:8]}", api_key_hash,
        )
        ws = await pool.fetchrow(
            "INSERT INTO workspaces (name, creator_id, invite_code) VALUES ('whws', $1, $2) RETURNING id",
            user["id"], uuid.uuid4().hex[:12],
        )

        from backend.services.webhook_service import create_webhook
        secret = "mysupersecret"
        with patch("socket.getaddrinfo", _fake_getaddrinfo_public):
            wh = await create_webhook(ws["id"], user["id"], "https://hooks.example.com/post", secret=secret)

        # Verify the hash is correct
        expected_hash = hashlib.sha256(secret.encode()).hexdigest()
        row = await pool.fetchrow(
            "SELECT secret_hash FROM webhooks WHERE id = $1", wh["id"]
        )
        assert row["secret_hash"] == expected_hash

        # Verify the response does not expose the hash
        assert "secret_hash" not in wh
        assert wh["has_secret"] is True

    @pytest.mark.asyncio
    async def test_no_secret_has_secret_false(self, pool):
        import uuid
        api_key_hash = "hash_" + uuid.uuid4().hex
        user = await pool.fetchrow(
            "INSERT INTO users (name, type, api_key_hash) VALUES ($1, 'human', $2) RETURNING id",
            f"whtest2_{uuid.uuid4().hex[:8]}", api_key_hash,
        )
        ws = await pool.fetchrow(
            "INSERT INTO workspaces (name, creator_id, invite_code) VALUES ('whws2', $1, $2) RETURNING id",
            user["id"], uuid.uuid4().hex[:12],
        )
        from backend.services.webhook_service import create_webhook
        with patch("socket.getaddrinfo", _fake_getaddrinfo_public):
            wh = await create_webhook(ws["id"], user["id"], "https://hooks.example.com/post")
        assert wh["has_secret"] is False
