from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet, InvalidToken

from backend.integrations import crypto as integration_crypto
from backend.integrations import storage
from backend.integrations.base import AccountInfo, TokenSet
from backend.integrations.granola import oauth as granola_oauth
from backend.services import user_service


def test_integration_keyring_decrypts_previous_key_and_encrypts_with_primary(monkeypatch):
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    monkeypatch.setattr(integration_crypto.settings, "INTEGRATIONS_ENCRYPTION_KEY", old_key)
    old_ciphertext = integration_crypto.integration_fernet().encrypt(b"existing-token")

    monkeypatch.setattr(
        integration_crypto.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        f"{new_key},{old_key}",
    )

    assert storage._decrypt(old_ciphertext) == "existing-token"

    new_ciphertext = storage._encrypt("new-token")
    assert new_ciphertext is not None
    assert Fernet(new_key.encode()).decrypt(new_ciphertext).decode() == "new-token"

    try:
        Fernet(old_key.encode()).decrypt(new_ciphertext)
    except InvalidToken:
        pass
    else:
        raise AssertionError("new tokens must be encrypted with the primary key")


def test_integration_keyring_decodes_oauth_state_from_previous_key(monkeypatch):
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    monkeypatch.setattr(integration_crypto.settings, "INTEGRATIONS_ENCRYPTION_KEY", old_key)
    state = granola_oauth._encode_state(
        UUID(int=1),
        "/settings",
        "verifier",
        {"client_id": "client_abc"},
    )

    monkeypatch.setattr(
        integration_crypto.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        f"{new_key},{old_key}",
    )

    payload = granola_oauth._decode_state(state)
    assert payload["u"] == str(UUID(int=1))
    assert payload["r"] == "/settings"


def test_invalid_integration_keyring_does_not_reuse_previous_cache(monkeypatch):
    monkeypatch.setattr(
        integration_crypto.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    integration_crypto.integration_fernet()

    monkeypatch.setattr(
        integration_crypto.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        "not-a-fernet-key",
    )

    assert (
        integration_crypto.integration_keyring_error()
        == "INTEGRATIONS_ENCRYPTION_KEY must be one or more valid Fernet keys."
    )


@pytest.mark.asyncio
async def test_revoke_stored_deletes_local_credentials_when_keyring_is_broken(
    monkeypatch,
    pool,
):
    user, _api_key = await user_service.register_user(
        name=f"disconnect_{uuid4().hex[:8]}",
        display_name="Webflow User",
        password="securepassword1",
    )
    user_id = user["id"]

    monkeypatch.setattr(
        integration_crypto.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    await storage.store_token(
        user_id,
        "github",
        TokenSet(
            access_token="customer-access-token",
            refresh_token=None,
            expires_at=None,
            scopes=["repo"],
        ),
        AccountInfo(email="user@example.com", display_name="Webflow User"),
    )

    monkeypatch.setattr(
        integration_crypto.settings,
        "INTEGRATIONS_ENCRYPTION_KEY",
        "not-a-fernet-key",
    )

    await storage.revoke_stored(user_id, "github")

    remaining = await pool.fetchval(
        "SELECT COUNT(*) FROM user_integrations WHERE user_id = $1 AND provider = 'github'",
        user_id,
    )
    assert remaining == 0
