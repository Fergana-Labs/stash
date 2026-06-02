"""Notion integration: OAuth provider.

Notion pages/databases are a connected source — indexed into notion_index by
backend/integrations/notion/indexer.py (dispatched from backend/tasks/sources),
not imported into the native file system.
"""

from ..registry import register_provider
from .provider import NotionIntegration

register_provider(NotionIntegration())
