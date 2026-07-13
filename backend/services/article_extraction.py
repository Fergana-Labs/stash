"""Extract the readable article from raw page HTML.

One extractor for every clip path: the browser extension sends the DOM it
captured, the URL-import worker sends fetched HTML — both land here. A page
that yields no article is a loud, typed error; there is deliberately no
fallback extractor.
"""

import trafilatura


class ArticleExtractionError(Exception):
    """The HTML has no extractable article content."""


def extract_article(html: str, url: str) -> dict:
    """Return {"title": str | None, "markdown": str}.

    Raises ArticleExtractionError when the page has no article body
    (navigation pages, empty shells, login walls).
    """
    markdown = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_images=True,
    )
    if not markdown or not markdown.strip():
        raise ArticleExtractionError("Could not extract an article from this page")
    meta = trafilatura.extract_metadata(html, default_url=url)
    title = meta.title if meta else None
    return {"title": title, "markdown": markdown}
