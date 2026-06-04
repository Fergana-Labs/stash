"""Asana integration: OAuth provider.

A connected Asana project is indexed into asana_documents by
backend/integrations/asana/indexer.py (dispatched from backend/tasks/sources) —
each task becomes a navigable document.
"""

from ..registry import register_provider
from .provider import AsanaIntegration

register_provider(AsanaIntegration())
