"""
Fetch YouTube Data API v3 statistics for a video (e.g. view count).

Used for on-demand GET /youtube/vroom-vroom: fetches current view count,
stores it as a snapshot metric, and returns JSON. API key via YOUTUBE_API_KEY env.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

# Official Charli XCX "Vroom Vroom" music video. Override with YOUTUBE_VIDEO_ID env.
DEFAULT_VIDEO_ID = "qfAqtFuGjWM"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeFetcherError(Exception):
    """Raised when the YouTube API key is missing or the API request fails."""


def get_video_statistics(
    *,
    api_key: str | None = None,
    video_id: str | None = None,
) -> dict[str, int]:
    """
    Fetch view count and like count for a YouTube video via Data API v3 (one request).

    Returns:
        {"view_count": int, "like_count": int}. like_count is 0 if the API omits it (e.g. likes disabled).

    Raises:
        YouTubeFetcherError: If key is missing, request fails, or response has no statistics.
    """
    key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not key or not key.strip():
        raise YouTubeFetcherError("YOUTUBE_API_KEY environment variable is not set")

    vid = video_id or os.environ.get("YOUTUBE_VIDEO_ID") or DEFAULT_VIDEO_ID
    params = {"part": "statistics", "id": vid, "key": key}
    url = f"{YOUTUBE_VIDEOS_URL}?{urlencode(params)}"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("YouTube API request failed: %s", e)
        raise YouTubeFetcherError(f"YouTube API request failed: {e}") from e

    data = resp.json()
    if "error" in data:
        err = data["error"]
        code = err.get("code")
        msg = "; ".join(m.get("reason", "") or "" for m in err.get("errors", []))
        raise YouTubeFetcherError(f"YouTube API error (code={code}): {msg or data}")

    items = data.get("items") or []
    if not items:
        raise YouTubeFetcherError(f"No video found for id={vid}")

    stats = items[0].get("statistics") or {}
    view_count_str = stats.get("viewCount")
    if view_count_str is None:
        raise YouTubeFetcherError("Video statistics do not include viewCount")

    try:
        view_count = int(view_count_str)
    except (TypeError, ValueError) as e:
        raise YouTubeFetcherError(f"Invalid viewCount value: {view_count_str}") from e

    like_count_str = stats.get("likeCount")
    try:
        like_count = int(like_count_str) if like_count_str is not None else 0
    except (TypeError, ValueError):
        like_count = 0

    return {"view_count": view_count, "like_count": like_count}


def get_view_count(*, api_key: str | None = None, video_id: str | None = None) -> int:
    """
    Fetch the view count for a YouTube video via Data API v3.
    Convenience wrapper around get_video_statistics() for callers that only need views.
    """
    return get_video_statistics(api_key=api_key, video_id=video_id)["view_count"]
