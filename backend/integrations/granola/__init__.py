"""Granola integration: OAuth provider.

Granola notes are a connected source — indexed into granola_notes by
backend/integrations/granola/indexer.py on the scheduled-pull path (a webhook
can be added once Granola webhook support is confirmed). Business/Enterprise
gated; inert until GRANOLA_OAUTH_* env vars are set.
"""

from ..registry import register_provider
from .provider import GranolaIntegration

register_provider(GranolaIntegration())
