"""
Tests for TokenService (app/services/token_service.py).

Covers: verify token store/get/expire/consume, user authorization,
camera token store/get/expire.
"""

import time
from unittest.mock import patch, MagicMock

import pytest


# ------------------------------------------------------------------
# Helpers — build a fake Datastore that TokenService can talk to
# ------------------------------------------------------------------


class FakeEntity(dict):
    def __init__(self, key, data=None):
        super().__init__(data or {})
        self.key = key


class InMemoryDS:
    """Minimal Datastore double."""

    def __init__(self):
        self._store = {}

    def key(self, kind, name=None):
        return (kind, name)

    def put(self, entity):
        self._store[entity.key] = entity

    def get(self, key):
        return self._store.get(key)

    def delete(self, key):
        self._store.pop(key, None)


@pytest.fixture()
def ts(app):
    """Return a TokenService wired to an in-memory Datastore."""
    from app.services.token_service import TokenService

    svc = TokenService()
    ds = InMemoryDS()
    svc._ds_client = ds

    # Provide the real app context for config access
    with app.app_context():
        yield svc


# ------------------------------------------------------------------
# Verify tokens
# ------------------------------------------------------------------


class TestVerifyTokens:
    @patch("app.services.token_service.get_datastore_client")
    def test_expired_auto_deleted(self, mock_client, app):
        from tests.conftest import FakeDatastoreClient, FakeEntity, FakeKey
        ds = FakeDatastoreClient()
        mock_client.return_value = ds
        # Seed an explicitly expired token
        entity = FakeEntity(FakeKey("CameraToken", "expired_cam"), {
            "user_id": "U3",
            "expiry": 1000  # long ago
        })
        ds._store.setdefault("CameraToken", {})["expired_cam"] = entity
        
        with app.app_context():
            from app.services.token_service import token_service
            uid, exp = token_service.get_camera_token("expired_cam")
            
        assert uid is None
        assert "expired_cam" not in ds._store.get("CameraToken", {})

    def test_store_and_get(self, ts):
        ts.store_verify_token("tok1", "Uabc", "open")
        user_id, expiry, action = ts.get_verify_token("tok1")
        assert user_id == "Uabc"
        assert action == "open"
        assert expiry is not None

    def test_consumed_on_read(self, ts):
        """Token should be deleted after first get."""
        ts.store_verify_token("tok2", "Uabc", "close")
        ts.get_verify_token("tok2")
        user_id, _, _ = ts.get_verify_token("tok2")
        assert user_id is None

    def test_expired_returns_none(self, ts, app):
        app.config["VERIFY_TTL"] = 0  # expire immediately
        ts.store_verify_token("tok3", "Uabc", "open")
        # Force expiry by sleeping briefly
        import time
        time.sleep(0.05)
        user_id, _, _ = ts.get_verify_token("tok3")
        assert user_id is None
        app.config["VERIFY_TTL"] = 300  # restore


# ------------------------------------------------------------------
# User authorization
# ------------------------------------------------------------------


class TestUserAuthorization:
    def test_authorize_and_check(self, ts):
        ts.authorize_user("U1")
        assert ts.is_user_authorized("U1") is True

    def test_not_authorized(self, ts):
        assert ts.is_user_authorized("Uunknown") is False

    def test_expired_authorization(self, ts, app):
        app.config["LOCATION_TTL"] = 0
        ts.authorize_user("U2")
        time.sleep(0.05)
        assert ts.is_user_authorized("U2") is False
        app.config["LOCATION_TTL"] = 300


# ------------------------------------------------------------------
# Camera tokens
# ------------------------------------------------------------------


class TestCameraTokens:
    def test_store_and_get(self, ts):
        ts.store_camera_token("cam1", "U1")
        user_id, expiry = ts.get_camera_token("cam1")
        assert user_id == "U1"

    def test_expired_auto_deleted(self, ts, app):
        app.config["CAMERA_TOKEN_TTL"] = 0
        ts.store_camera_token("cam2", "U1")
        time.sleep(0.05)
        user_id, _ = ts.get_camera_token("cam2")
        assert user_id is None
        app.config["CAMERA_TOKEN_TTL"] = 3600


class TestTokenServiceExceptions:
    @patch("app.services.token_service.get_datastore_client")
    def test_store_verify_token_exception(self, mock_client, app):
        mock_client.return_value.put.side_effect = Exception("DB error")
        with app.app_context():
            from app.services.token_service import token_service
            assert token_service.store_verify_token("tok", "U1", "open") is False

    @patch("app.services.token_service.get_datastore_client")
    def test_get_verify_token_exception(self, mock_client, app):
        mock_client.return_value.get.side_effect = Exception("DB error")
        with app.app_context():
            from app.services.token_service import token_service
            assert token_service.get_verify_token("tok") == (None, None, None)

    @patch("app.services.token_service.get_datastore_client")
    def test_authorize_user_exception(self, mock_client, app):
        mock_client.return_value.put.side_effect = Exception("DB error")
        with app.app_context():
            from app.services.token_service import token_service
            assert token_service.authorize_user("U1") is False

    @patch("app.services.token_service.get_datastore_client")
    def test_is_user_authorized_exception(self, mock_client, app):
        mock_client.return_value.get.side_effect = Exception("DB error")
        with app.app_context():
            from app.services.token_service import token_service
            assert token_service.is_user_authorized("U1") is False

    @patch("app.services.token_service.get_datastore_client")
    def test_store_camera_token_exception(self, mock_client, app):
        mock_client.return_value.put.side_effect = Exception("DB error")
        with app.app_context():
            from app.services.token_service import token_service
            assert token_service.store_camera_token("tok", "U1") is False

    @patch("app.services.token_service.get_datastore_client")
    def test_get_camera_token_exception(self, mock_client, app):
        mock_client.return_value.get.side_effect = Exception("DB error")
        with app.app_context():
            from app.services.token_service import token_service
            uid, exp = token_service.get_camera_token("bad_token")
            assert uid is None
            assert exp is None

    def test_init_app(self):
        from app.services.token_service import TokenService
        mock_app = MagicMock()
        ts = TokenService(app=mock_app)
        assert ts is not None
