"""Jira integration: OAuth provider.

A connected Jira project is indexed into jira_documents by
backend/integrations/jira/indexer.py (dispatched from backend/tasks/sources) —
each issue becomes a searchable document.
"""

from ..registry import register_provider
from .provider import JiraIntegration

register_provider(JiraIntegration())
