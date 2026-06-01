"""Slack integration: OAuth provider.

Slack is a connected, push-subscribed source: a one-time backfill indexes
history into source_documents, then the Events API webhook
(backend/routers/webhooks.py) streams new messages in. Indexer +
event-ingest live in backend/tasks/sources.
"""

from ..registry import register_provider
from .provider import SlackIntegration

register_provider(SlackIntegration())
