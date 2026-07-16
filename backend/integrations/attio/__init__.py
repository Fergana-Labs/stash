"""Attio integration: OAuth provider (standard authorization-code app).

Connected Attio call recordings are indexed into attio_documents by
backend/integrations/attio/indexer.py (dispatched from backend/tasks/sources) —
each recording's transcript becomes a searchable document.
"""

from ..registry import register_provider
from .provider import AttioIntegration

register_provider(AttioIntegration())
