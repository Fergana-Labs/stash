"""Gmail integration: OAuth provider + index-only mailbox source.

A connected Gmail mailbox is indexed into gmail_index by
backend/integrations/gmail/indexer.py (dispatched from backend/tasks/sources).
Search is federated to Gmail and message bodies are fetched lazily on read.
"""

from ..registry import register_provider
from .provider import GmailIntegration

register_provider(GmailIntegration())
