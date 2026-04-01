"""
Tests for the app factory (app/__init__.py).

Covers: health check, security headers, config validation.
"""

from unittest.mock import patch

import pytest


class TestHealthCheck:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestSecurityHeaders:
    def test_headers_present(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert resp.headers.get("X-Frame-Options") == "DENY"
    def test_missing_secrets_raises(self):
        """Config.validate() should raise if LINE secrets are missing."""
        from app.config import Config

        original_token = Config.LINE_CHANNEL_ACCESS_TOKEN
        original_secret = Config.LINE_CHANNEL_SECRET
        try:
            Config.LINE_CHANNEL_ACCESS_TOKEN = None
            Config.LINE_CHANNEL_SECRET = None
            with pytest.raises(RuntimeError, match="Missing required secrets"):
                Config.validate()
        finally:
            Config.LINE_CHANNEL_ACCESS_TOKEN = original_token
            Config.LINE_CHANNEL_SECRET = original_secret


class TestAppCreation:
    @patch("app.services.mqtt_service.create_mqtt_client")
    def test_rate_limiting_enabled(self, mock_mqtt):
        from app import create_app
        from app.config import Config
        
        class TestConfigOverrides(Config):
            RATE_LIMIT_ENABLED = True
            MAX_REQUESTS_PER_MINUTE = 100
            
        app = create_app(TestConfigOverrides)
        assert app.config["RATELIMIT_DEFAULT"] == "100 per minute"
