"""Twitter / X integration: OAuth provider.

Connected Twitter sources use X API v2 user-context reads. Recent-search
results are cached as index rows so agents can open individual posts with
read_source.
"""

from ..registry import register_provider
from .provider import TwitterIntegration

register_provider(TwitterIntegration())
