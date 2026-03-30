"""
youtube_service.py
Fetches the currently-live YouTube stream for a channel using the YouTube Data API v3.
Results are cached for CACHE_TTL seconds so every page-view doesn't cost an API quota unit.
"""

import time

import requests

from utils.logger_config import get_logger

logger = get_logger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
EMBED_BASE = "https://www.youtube.com/embed/"

# Cache: (video_id | None, fetched_at_timestamp)
_CACHE: dict = {"video_id": None, "fetched_at": 0.0}
CACHE_TTL = 60  # seconds


def _fetch_live_video_id(channel_id: str, api_key: str) -> str | None:
    """Call YouTube Data API v3 to find the active livestream for *channel_id*."""
    params = {
        "part": "id",
        "channelId": channel_id,
        "eventType": "live",
        "type": "video",
        "key": api_key,
    }
    try:
        resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=5)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            return items[0]["id"]["videoId"]
        logger.warning("No active live stream found for channel %s", channel_id)
        return None
    except requests.RequestException as exc:
        logger.error("YouTube API request failed: %s", exc)
        return None


def get_live_embed_url(channel_id: str, api_key: str) -> str | None:
    """
    Return the YouTube embed URL for the channel's current live stream.
    Returns None if the channel is not live or the API call fails.
    Results are cached for CACHE_TTL seconds.
    """
    now = time.monotonic()
    if now - _CACHE["fetched_at"] > CACHE_TTL:
        video_id = _fetch_live_video_id(channel_id, api_key)
        _CACHE["video_id"] = video_id
        _CACHE["fetched_at"] = now
        if video_id:
            logger.info("YouTube live stream resolved: video_id=%s", video_id)
        else:
            logger.warning("Channel %s has no active live stream", channel_id)

    video_id = _CACHE["video_id"]
    return f"{EMBED_BASE}{video_id}" if video_id else None
