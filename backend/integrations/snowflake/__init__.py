"""Snowflake integration: api_key provider.

Snowflake is a *queryable* source — the agent runs read-only SQL against it via
the source tools (see backend/integrations/snowflake/client.py). There is no
indexer or document table; queries run live.
"""

from ..registry import register_provider
from .provider import SnowflakeIntegration

register_provider(SnowflakeIntegration())
