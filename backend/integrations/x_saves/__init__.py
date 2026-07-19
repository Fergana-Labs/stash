"""X (Twitter) saves: an OAuth source.

The user connects X over OAuth 2.0 (PKCE). The indexer reads their bookmarks
from the X API with the stored token and pulls their own posts/replies from
twitterapi.io by account id; every tweet is hydrated (full text, reply thread
root, archived media) via twitterapi.io and served from the x_save_docs table.
"""

from ..registry import register_provider
from .provider import XIntegration

register_provider(XIntegration())
