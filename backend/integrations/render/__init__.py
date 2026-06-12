"""Render integration: api_key provider.

A connected Render key powers the MCP proxy
(backend/services/mcp_proxy_service.py): agents reach Render's read-only
MCP tools (services, deploys, logs, metrics) through /api/v1/mcp.
"""

from ..registry import register_provider
from .provider import RenderIntegration

register_provider(RenderIntegration())
