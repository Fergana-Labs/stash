"""Credential-based PostHog provider."""

from __future__ import annotations

import json
from urllib.parse import urlparse

import httpx

from ..base import AccountInfo, CredentialField, TokenSet

POSTHOG_CLOUD_HOSTS = {"us.posthog.com", "eu.posthog.com"}


def normalize_host(value: str) -> str:
    host = value.strip().rstrip("/")
    parsed = urlparse(host)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise ValueError("instance_url must be an HTTPS origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("instance_url must not contain credentials, a query, or a fragment")
    if parsed.hostname not in POSTHOG_CLOUD_HOSTS or parsed.port not in (None, 443):
        raise ValueError("instance_url must be a PostHog Cloud origin")
    return host


def decode_credentials(token: str) -> dict[str, str]:
    values = json.loads(token)
    return {
        "instance_url": values["instance_url"],
        "project_id": values["project_id"],
        "personal_api_key": values["personal_api_key"],
    }


class PostHogIntegration:
    name = "posthog"
    display_name = "PostHog"
    auth_kind = "api_key"
    scopes = ["project:read"]
    supports_refresh = False
    credential_fields = [
        CredentialField(
            "instance_url",
            "PostHog instance URL",
            placeholder="https://us.posthog.com",
            help="Use https://eu.posthog.com for EU Cloud.",
        ),
        CredentialField("project_id", "Project ID", placeholder="12345"),
        CredentialField(
            "personal_api_key",
            "Personal API key",
            secret=True,
            placeholder="phx_…",
            help="Create a key with project read access in PostHog settings.",
        ),
    ]

    async def connect_with_credentials(
        self, values: dict[str, str]
    ) -> tuple[TokenSet, AccountInfo]:
        required = ("instance_url", "project_id", "personal_api_key")
        if any(not values.get(field, "").strip() for field in required):
            raise ValueError("all PostHog credentials are required")

        instance_url = normalize_host(values["instance_url"])
        project_id = values["project_id"].strip()
        if not project_id.isascii() or not project_id.isdigit():
            raise ValueError("project_id must be numeric")
        personal_api_key = values["personal_api_key"].strip()
        headers = {"Authorization": f"Bearer {personal_api_key}"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            response = await client.get(f"{instance_url}/api/projects/{project_id}/")
            response.raise_for_status()
            project = response.json()

        if str(project.get("id")) != project_id:
            raise ValueError("PostHog returned a different project")
        token = json.dumps(
            {
                "instance_url": instance_url,
                "project_id": project_id,
                "personal_api_key": personal_api_key,
            }
        )
        project_name = project.get("name") or f"Project {project_id}"
        return (
            TokenSet(
                access_token=token,
                refresh_token=None,
                expires_at=None,
                scopes=list(self.scopes),
            ),
            AccountInfo(email=None, display_name=project_name),
        )

    async def revoke(self, access_token: str) -> None:
        return None
