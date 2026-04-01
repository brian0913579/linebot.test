"""
Tests for the YouTube service (app/services/youtube_service.py).

Covers: live stream resolution, caching, error handling.
"""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the module-level cache between tests."""
    from app.services import youtube_service
    youtube_service._CACHE["video_id"] = None
    youtube_service._CACHE["fetched_at"] = 0.0
    yield


class TestGetLiveEmbedUrl:
    @patch("app.services.youtube_service.requests.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [{"id": {"videoId": "abc123"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.youtube_service import get_live_embed_url
        url = get_live_embed_url("UC_test", "key123")

        assert url == "https://www.youtube.com/embed/abc123"

    @patch("app.services.youtube_service.requests.get")
    def test_no_stream_returns_none(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.youtube_service import get_live_embed_url
        url = get_live_embed_url("UC_test", "key123")

        assert url is None

    @patch("app.services.youtube_service.requests.get")
    def test_cache_hit_no_extra_api_call(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [{"id": {"videoId": "cached1"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from app.services.youtube_service import get_live_embed_url
        get_live_embed_url("UC_test", "key123")
        get_live_embed_url("UC_test", "key123")

        assert mock_get.call_count == 1  # only one API call despite two invocations

    @patch("app.services.youtube_service.requests.get")
    def test_api_error_returns_none(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("timeout")

        from app.services.youtube_service import get_live_embed_url
        url = get_live_embed_url("UC_test", "key123")

        assert url is None
