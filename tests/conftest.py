"""
Shared fixtures for the LINE Bot test suite.

All external dependencies (Datastore, LINE API, MQTT, YouTube API) are mocked
so tests run locally without credentials or network access.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Prevent real GCP clients from initialising during import
# ---------------------------------------------------------------------------
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
os.environ.setdefault("LINE_CHANNEL_SECRET", "test-secret")
os.environ.setdefault("SECRETS_BACKEND", "env")


# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------
class TestConfig:
    """Flask config for testing — no real secrets needed."""

    TESTING = True
    SECRET_KEY = "test-secret-key"

    # LINE
    LINE_CHANNEL_ACCESS_TOKEN = "test-token"
    LINE_CHANNEL_SECRET = "test-secret"

    # MQTT
    MQTT_BROKER = "localhost"
    MQTT_PORT = 8883
    MQTT_USERNAME = "testuser"
    MQTT_PASSWORD = "testpass"
    MQTT_TOPIC = "garage/command"

    # Location
    PARK_LAT = 24.79155
    PARK_LNG = 120.99442
    MAX_DIST_KM = 1.0
    MAX_ACCURACY_METERS = 250
    VERIFY_TTL = 300
    LOCATION_TTL = 300
    CAMERA_TOKEN_TTL = 3600

    # URLs
    VERIFY_URL_BASE = "http://localhost/static/verify.html"
    APP_BASE_URL = "http://localhost"
    YOUTUBE_LIVE_URL = ""
    YOUTUBE_CHANNEL_ID = ""
    YOUTUBE_API_KEY = ""

    # Security
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "testpass123"
    RATE_LIMIT_ENABLED = False
    MAX_REQUESTS_PER_MINUTE = 30

    # Debug
    DEBUG_MODE = False
    DEBUG_USER_IDS = []

    @classmethod
    def validate(cls):
        pass  # Skip validation in tests


# ---------------------------------------------------------------------------
# Datastore mock helpers
# ---------------------------------------------------------------------------
class FakeEntity(dict):
    """Mimics a google.cloud.datastore.Entity with a .key attribute."""

    def __init__(self, key, data=None):
        super().__init__(data or {})
        self.key = key


class FakeKey:
    def __init__(self, kind, name=None):
        self.kind = kind
        self.name = name

    def __repr__(self):
        return f"FakeKey({self.kind!r}, {self.name!r})"


class FakeDatastoreClient:
    """In-memory fake for google.cloud.datastore.Client."""

    def __init__(self):
        self._store: dict[str, dict[str, FakeEntity]] = {}

    def key(self, kind, name=None):
        return FakeKey(kind, name)

    def put(self, entity):
        kind = entity.key.kind
        name = entity.key.name
        self._store.setdefault(kind, {})[name] = entity

    def get(self, key):
        return self._store.get(key.kind, {}).get(key.name)

    def delete(self, key):
        self._store.get(key.kind, {}).pop(key.name, None)

    def query(self, kind):
        return FakeQuery(self._store.get(kind, {}))


class FakeQuery:
    def __init__(self, bucket):
        self._bucket = bucket

    def fetch(self):
        return list(self._bucket.values())


def _fake_entity_constructor(key, **kwargs):
    return FakeEntity(key)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def fake_ds():
    """Return a FakeDatastoreClient and patch google.cloud.datastore."""
    client = FakeDatastoreClient()
    with patch("google.cloud.datastore.Client", return_value=client), \
         patch("google.cloud.datastore.Entity", side_effect=_fake_entity_constructor):
        yield client


@pytest.fixture()
def app(fake_ds):
    """Create a Flask test app with mocked LINE SDK and Datastore."""
    mock_api = MagicMock()
    mock_handler = MagicMock()
    # Make the decorator transparent so handle_text does not turn into a MagicMock
    mock_handler.add.side_effect = lambda *args, **kwargs: lambda f: f

    with patch("app.services.line_service.MessagingApi", return_value=mock_api), \
         patch("app.services.line_service.WebhookHandler", return_value=mock_handler), \
         patch("app.services.line_service.ApiClient"), \
         patch("app.services.mqtt_service.mqtt.Client"):

        from app import create_app

        application = create_app(config_class=TestConfig)
        application.config["line_bot_api_mock"] = mock_api
        application.config["webhook_handler_mock"] = mock_handler
        yield application


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def mock_mqtt():
    """Patch paho MQTT Client with a fake that appears connected."""
    fake_client = MagicMock()
    fake_client.is_connected.return_value = True

    fake_result = MagicMock()
    fake_result.is_published.return_value = True
    fake_client.publish.return_value = fake_result

    with patch("app.services.mqtt_service.mqtt.Client", return_value=fake_client):
        yield fake_client
