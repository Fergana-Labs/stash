"""Fetch a YouTube video's transcript via ScrapeCreators.

Server-side yt-dlp was the old path; YouTube bot-detects datacenter IPs,
which is fatal at bulk-import scale (a real bookmark export is a quarter
YouTube). The transcript comes from ScrapeCreators — the same vendor,
key, and header as Instagram saves — and the title/channel from YouTube's
official oEmbed endpoint, which is key-free and not bot-gated. oEmbed is
checked first: it failing means the video is private or deleted, so no
transcript can exist and no ScrapeCreators credit should be spent.
"""

import httpx

from ..config import settings

SC_TRANSCRIPT_URL = "https://api.scrapecreators.com/v1/youtube/video/transcript"
OEMBED_URL = "https://www.youtube.com/oembed"

# ScrapeCreators may transcribe on demand; give it room.
_TIMEOUT = 90


class TranscriptUnavailable(Exception):
    """The video is private/deleted or has no usable caption track."""


async def fetch_transcript(url: str) -> dict:
    """Return {"title", "channel", "transcript"} for a YouTube URL."""
    if not settings.SCRAPECREATORS_API_KEY:
        raise RuntimeError("SCRAPECREATORS_API_KEY is not set")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        oembed = await client.get(OEMBED_URL, params={"url": url, "format": "json"})
        if oembed.status_code != 200:
            raise TranscriptUnavailable(
                f"Video is private or deleted (oEmbed HTTP {oembed.status_code})"
            )
        meta = oembed.json()

        sc = await client.get(
            SC_TRANSCRIPT_URL,
            params={"url": url},
            headers={"x-api-key": settings.SCRAPECREATORS_API_KEY},
        )
        sc.raise_for_status()
        transcript = sc.json().get("transcript_only_text")
        if not transcript:
            raise TranscriptUnavailable("No transcript available for this video")

    return {
        "title": meta["title"],
        "channel": meta["author_name"],
        "transcript": transcript,
    }
