"""Network controls for HTML export renderers."""

from __future__ import annotations

from playwright.async_api import Route


async def abort_network_request(route: Route) -> None:
    await route.abort()
