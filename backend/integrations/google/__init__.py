"""Google integration: OAuth provider + Google Slides export.

Drive is a connected source — indexed into source_documents by
backend/integrations/google/indexer.py (dispatched from backend/tasks/sources),
not imported into the native file system.
"""

from ..registry import register_provider
from .provider import GoogleIntegration

register_provider(GoogleIntegration())
