"""Linear integration: OAuth provider.

A connected Linear account is synced as a data source: the indexer in
backend/integrations/linear/indexer.py lists, reads, and searches the
issues the connected user can see under /sources.
"""

from ..registry import register_provider
from .provider import LinearIntegration

register_provider(LinearIntegration())
