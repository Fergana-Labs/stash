"""Instagram saves: a provider-less source type.

There is no OAuth integration to register — the private "what did I save"
list comes from the browser extension (logged into instagram.com), and the
public content is hydrated server-side via ScrapeCreators with a
product-level API key. Only the indexer lives here.
"""
