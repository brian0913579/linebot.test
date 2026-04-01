"""
Tests for camera access (app/api/camera.py).

Covers: token gating, whitelist check, YouTube URL resolution, error pages.
"""

from unittest.mock import patch, MagicMock

import pytest


class TestCameraView:
    def test_no_token_returns_403(self, client):
        resp = client.get("/camera")
        assert resp.status_code == 403

    @patch("app.api.camera.token_service")
    def test_invalid_token_returns_403(self, mock_ts, client):
        mock_ts.get_camera_token.return_value = (None, None)
        resp = client.get("/camera?token=badtoken")
        assert resp.status_code == 403

    @patch("app.api.camera.get_allowed_users", return_value={})
    @patch("app.api.camera.token_service")
    def test_revoked_user_returns_403(self, mock_ts, mock_users, client):
        mock_ts.get_camera_token.return_value = ("Urevoked", 9999999999)
        resp = client.get("/camera?token=tok1")
        assert resp.status_code == 403

    @patch("app.api.camera.get_allowed_users", return_value={"Uok": "Alice"})
    @patch("app.api.camera.token_service")
    def test_valid_token_with_static_url(self, mock_ts, mock_users, client, app):
        mock_ts.get_camera_token.return_value = ("Uok", 9999999999)
        with app.app_context():
            app.config["YOUTUBE_LIVE_URL"] = "https://youtube.com/embed/STATIC123"
            resp = client.get("/camera?token=T1")
            assert resp.status_code == 200
            assert "youtube.com/embed/STATIC123" in resp.text
            
    @patch("app.api.camera.token_service")
    @patch("app.api.camera.get_allowed_users", return_value={"U1": "Alice"})
    def test_si_param_stripped(self, mock_users, mock_ts, client, app):
        mock_ts.get_camera_token.return_value = ("U1", 9999999999)
        with app.app_context():
            app.config["YOUTUBE_CHANNEL_ID"] = None
            app.config["YOUTUBE_LIVE_URL"] = "https://youtube.com/embed/STATIC123?si=123"
            resp = client.get("/camera?token=T1")
            assert resp.status_code == 200
            assert "si=123" not in resp.text

    @patch("app.api.camera.token_service")
    @patch("app.api.camera.get_allowed_users", return_value={"U1": "Alice"})
    def test_no_sources_configured_returns_503(self, mock_nau, mock_ts, client, app):
        mock_ts.get_camera_token.return_value = ("U1", 9999999999)
        with app.app_context():
            from app.api.camera import generate_camera_token
            generate_camera_token("U1")
            
            app.config["YOUTUBE_CHANNEL_ID"] = None
            app.config["YOUTUBE_LIVE_URL"] = None
            resp = client.get("/camera?token=T1")
            assert resp.status_code == 503

    @patch("app.services.youtube_service.get_live_embed_url", return_value=None)
    @patch("app.api.camera.get_allowed_users", return_value={"Uok": "Alice"})
    @patch("app.api.camera.token_service")
    def test_no_live_stream_returns_503(self, mock_ts, mock_users, mock_yt, client, app):
        mock_ts.get_camera_token.return_value = ("Uok", 9999999999)
        app.config["YOUTUBE_CHANNEL_ID"] = "UCtest"
        app.config["YOUTUBE_API_KEY"] = "key123"
        resp = client.get("/camera?token=tok1")
        assert resp.status_code == 503
        app.config["YOUTUBE_CHANNEL_ID"] = ""
        app.config["YOUTUBE_API_KEY"] = ""
