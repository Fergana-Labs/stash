"""Gong integration: OAuth provider (Gong Collective marketplace app).

Connected Gong calls are indexed into gong_documents by
backend/integrations/gong/indexer.py (dispatched from backend/tasks/sources) —
each call's transcript becomes a searchable document.
"""

from ..registry import register_provider
from .provider import GongIntegration

register_provider(GongIntegration())
