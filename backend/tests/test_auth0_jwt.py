"""Verify Auth0's real RSA token contract and reject algorithm-confusion attempts."""

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from backend.managed.auth0 import jwt as auth0


@pytest.fixture(scope="module")
def signing_keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def public_jwk(key, kid="current"):
    return jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


def claims(**changes):
    now = int(time.time())
    return {
        "sub": "google-oauth2|test-user",
        "iss": "https://tenant.example.com/",
        "aud": "stash-api",
        "iat": now,
        "exp": now + 300,
        **changes,
    }


@pytest.fixture
def configured(monkeypatch, signing_keys):
    monkeypatch.setattr(auth0.settings, "AUTH0_DOMAIN", "tenant.example.com")
    monkeypatch.setattr(auth0.settings, "AUTH0_AUDIENCE", "stash-api")
    monkeypatch.setattr(auth0, "_jwks_cache", {"keys": None, "fetched_at": 0.0})

    async def fetch():
        return {"keys": [public_jwk(signing_keys[0])]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fetch)
    return signing_keys[0]


async def rejected(token, detail="Invalid token"):
    with pytest.raises(HTTPException) as exc:
        await auth0.validate_auth0_token(token)
    assert exc.value.status_code == 401 and exc.value.detail == detail
    assert token not in exc.value.detail


@pytest.mark.parametrize(
    "audience", ["stash-api", ["stash-api", "https://tenant.example.com/userinfo"]]
)
async def test_real_rs256_auth0_tokens_and_audience_arrays(configured, audience):
    payload = claims(aud=audience)
    token = jwt.encode(payload, configured, algorithm="RS256", headers={"kid": "current"})
    assert await auth0.validate_auth0_token(token) == payload


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://attacker.example.com/"},
        {"iss": "https://tenant.example.com/.attacker"},
        {"aud": "another-api"},
        {"exp": 1},
        {"nbf": 4_000_000_000},
        {"sub": 123},
    ],
)
async def test_signed_tokens_still_require_valid_claims(configured, change):
    token = jwt.encode(claims(**change), configured, algorithm="RS256", headers={"kid": "current"})
    await rejected(token)


async def test_wrong_signature_is_rejected(configured, signing_keys):
    token = jwt.encode(claims(), signing_keys[1], algorithm="RS256", headers={"kid": "current"})
    await rejected(token)


@pytest.mark.parametrize("algorithm", ["none", "RS384"])
async def test_only_rs256_is_accepted(configured, algorithm):
    key = "" if algorithm == "none" else configured
    token = jwt.encode(claims(), key, algorithm=algorithm, headers={"kid": "current"})
    await rejected(token)


async def test_public_der_key_cannot_be_used_to_forge_hs256(configured):
    # The RSA public bytes are public information, not an HMAC secret. Build
    # the forged token directly so library signing guards cannot hide a decoder bug.
    der = configured.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

    message = encode({"alg": "HS256", "kid": "current"}) + b"." + encode(claims())
    signature = base64.urlsafe_b64encode(hmac.new(der, message, hashlib.sha256).digest()).rstrip(
        b"="
    )
    await rejected((message + b"." + signature).decode())


@pytest.mark.parametrize("broken", [{"n": "AA"}, {"n": None}, {"kty": "oct"}])
async def test_invalid_jwks_keys_are_redacted(configured, monkeypatch, broken):
    async def fetch():
        return {"keys": [public_jwk(configured) | broken]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fetch)
    token = jwt.encode(claims(), configured, algorithm="RS256", headers={"kid": "current"})
    await rejected(token)


async def test_unknown_kid_refreshes_once_then_accepts_rotated_key(
    configured, signing_keys, monkeypatch
):
    calls = []

    async def fetch():
        calls.append(auth0._jwks_cache["keys"])
        return {"keys": [public_jwk(signing_keys[0], "old" if len(calls) == 1 else "current")]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fetch)
    auth0._jwks_cache["keys"] = {"keys": [public_jwk(signing_keys[1], "old")]}
    payload = claims()
    token = jwt.encode(payload, configured, algorithm="RS256", headers={"kid": "current"})
    assert await auth0.validate_auth0_token(token) == payload
    assert len(calls) == 2 and calls[1] is None


async def test_unknown_kid_is_rejected_after_one_refresh(configured, monkeypatch):
    calls = []

    async def fetch():
        calls.append(True)
        return {"keys": [public_jwk(configured)]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fetch)
    token = jwt.encode(claims(), configured, algorithm="RS256", headers={"kid": "unknown"})
    await rejected(token, "Unknown key id")
    assert len(calls) == 2


async def test_malformed_token_and_missing_kid(configured):
    await rejected("raw-token-secret", "Malformed token")
    await rejected(jwt.encode(claims(), configured, algorithm="RS256"), "Missing kid")
