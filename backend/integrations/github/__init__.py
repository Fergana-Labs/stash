"""GitHub integration: OAuth provider.

Connected GitHub repos are indexed into github_documents by
backend/integrations/github/indexer.py (dispatched from backend/tasks/sources) —
they are a connected source, not imported into the native file system.
"""

from ..registry import register_provider
from .provider import GitHubIntegration

register_provider(GitHubIntegration())
