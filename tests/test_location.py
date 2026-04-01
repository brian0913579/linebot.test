"""
Tests for location verification (app/api/location.py).

Covers: haversine formula, geofence logic, token validation, MQTT trigger,
debug-mode bypass.
"""

import time
from unittest.mock import patch, MagicMock

import pytest


# ------------------------------------------------------------------
# Haversine
# ------------------------------------------------------------------

class TestHaversine:
    def test_known_distance(self, app):
        """Check haversine against a well-known pair (~111 km per degree)."""
        from app.api.location import haversine
        dist = haversine(0, 0, 1, 0)
        assert 110 < dist < 112  # ~111.2 km

    def test_same_point(self, app):
        from app.api.location import haversine
        assert haversine(24.79, 120.99, 24.79, 120.99) == 0.0


# ------------------------------------------------------------------
# /api/verify-location
# ------------------------------------------------------------------

class TestVerifyLocation:

    def test_missing_token(self, client):
        resp = client.post(
            "/api/verify-location",
            json={"lat": 24.79, "lng": 120.99},
        )
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    @patch("app.api.location.token_service")
    def test_expired_token(self, mock_ts, client):
        mock_ts.get_verify_token.return_value = ("Utest", time.time() - 10, "open")
        resp = client.post(
            "/api/verify-location?token=tok123",
            json={"lat": 24.79, "lng": 120.99},
        )
        assert resp.status_code == 400
        assert "過期" in resp.get_json()["message"]

    @patch("app.api.location.token_service")
    def test_invalid_coords(self, mock_ts, client):
        mock_ts.get_verify_token.return_value = ("Utest", time.time() + 300, "open")
        resp = client.post(
            "/api/verify-location?token=tok123",
            json={"lat": "bad", "lng": 120.99},
        )
        assert resp.status_code == 400

    @patch("app.api.location.send_garage_command", return_value=(True, None))
    @patch("app.api.location.token_service")
    def test_inside_geofence_success(self, mock_ts, mock_mqtt, client, app):
        mock_ts.get_verify_token.return_value = ("Utest", time.time() + 300, "open")
        # Use the configured park coordinates (inside geofence)
        resp = client.post(
            "/api/verify-location?token=tok123",
            json={
                "lat": app.config["PARK_LAT"],
                "lng": app.config["PARK_LNG"],
                "acc": 10,
            },
        )
        data = resp.get_json()
        assert data["ok"] is True
        mock_ts.authorize_user.assert_called_once_with("Utest")
        mock_mqtt.assert_called_once_with("open")

    @patch("app.api.location.send_garage_command")
    @patch("app.api.location.token_service")
    def test_outside_geofence(self, mock_ts, mock_mqtt, client):
        mock_ts.get_verify_token.return_value = ("Utest", time.time() + 300, "open")
        # Tokyo: ~2000 km away
        resp = client.post(
            "/api/verify-location?token=tok123",
            json={"lat": 35.6762, "lng": 139.6503, "acc": 10},
        )
        data = resp.get_json()
        assert data["ok"] is False
        assert "不在" in data["message"]
        mock_mqtt.assert_not_called()

    @patch("app.api.location.send_garage_command", return_value=(False, "timeout"))
    @patch("app.api.location.token_service")
    def test_mqtt_failure_returns_500(self, mock_ts, mock_mqtt, client, app):
        mock_ts.get_verify_token.return_value = ("Utest", time.time() + 300, "close")
        resp = client.post(
            "/api/verify-location?token=tok123",
            json={
                "lat": app.config["PARK_LAT"],
                "lng": app.config["PARK_LNG"],
                "acc": 10,
            },
        )
        assert resp.status_code == 500

    @patch("app.api.location.send_garage_command", return_value=(True, None))
    @patch("app.api.location.token_service")
    def test_debug_user_bypass(self, mock_ts, mock_mqtt, client, app):
        app.config["DEBUG_MODE"] = True
        app.config["DEBUG_USER_IDS"] = ["Udebug"]
        mock_ts.get_verify_token.return_value = ("Udebug", time.time() + 300, "open")
        # Coordinates far from geofence — but debug user bypasses
        resp = client.post(
            "/api/verify-location?token=tok123",
            json={"lat": 0.0, "lng": 0.0, "acc": 10},
        )
        assert resp.get_json()["ok"] is True
        # Restore
        app.config["DEBUG_MODE"] = False
        app.config["DEBUG_USER_IDS"] = []
