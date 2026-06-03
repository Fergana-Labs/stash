"""Granola integration: OAuth 2.0 via the official MCP server.

Granola connects through `mcp.granola.ai` over OAuth 2.0 (Dynamic Client
Registration + PKCE) — browser sign-in, no pasted key. Meetings are a connected
source, pulled into granola_notes by indexer.py through the MCP tools
(`list_meetings` + `get_meeting_transcript`). See oauth.py for the handshake.
"""

from ..registry import register_provider
from .provider import GranolaIntegration

register_provider(GranolaIntegration())
