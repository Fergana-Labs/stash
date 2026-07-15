"""Fetch a YouTube video's transcript without downloading the video.

yt-dlp resolves metadata and caption tracks; the chosen track's json3
payload is fetched directly. Track choice is one deterministic rule —
manual captions beat auto-generated ones, English beats the video's
original language — with no cascade beyond that: a video with neither is
a loud TranscriptUnavailable.

Everything here is synchronous (yt-dlp is blocking); callers run it in a
worker thread.
"""

import httpx
import yt_dlp


class TranscriptUnavailable(Exception):
    """The video has no usable caption track."""


_FETCH_TIMEOUT = 30


def fetch_transcript(url: str) -> dict:
    """Return {"title", "channel", "transcript"} for a YouTube URL."""
    options = {"skip_download": True, "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    track = _pick_track(
        info.get("subtitles") or {},
        info.get("automatic_captions") or {},
        info.get("language"),
    )
    if track is None:
        raise TranscriptUnavailable("No transcript available for this video")

    json3_url = next((f["url"] for f in track if f.get("ext") == "json3"), None)
    if json3_url is None:
        raise TranscriptUnavailable("Caption track has no json3 format")
    response = httpx.get(json3_url, timeout=_FETCH_TIMEOUT)
    response.raise_for_status()

    return {
        "title": info.get("title") or url,
        "channel": info.get("channel") or info.get("uploader") or "",
        "transcript": _parse_json3(response.json()),
    }


def _pick_track(subtitles: dict, automatic: dict, original_language: str | None) -> list | None:
    """Manual captions beat auto-generated; English beats the original language."""
    for tracks in (subtitles, automatic):
        for prefix in ("en", original_language):
            if not prefix:
                continue
            for lang, formats in tracks.items():
                if lang.startswith(prefix):
                    return formats
    return None


def _parse_json3(payload: dict) -> str:
    """Flatten YouTube's json3 caption events to plain text."""
    lines: list[str] = []
    for event in payload.get("events", []):
        text = "".join(seg.get("utf8", "") for seg in event.get("segs", []))
        text = text.strip()
        if text:
            lines.append(text)
    transcript = " ".join(lines)
    if not transcript:
        raise TranscriptUnavailable("Caption track is empty")
    return transcript
