import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add the parent directory to sys.path to allow imports from the main project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Common fixtures for all tests


@pytest.fixture
def flask_app():
    """Fixture for Flask test client."""
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_line_bot_api():
    """Mock for the LINE Bot API client."""
    with patch("line_webhook.line_bot_api") as mock_api:
        yield mock_api


@pytest.fixture
def mock_mqtt_client():
    """Mock for the MQTT client."""
    with patch("mqtt_handler.mqtt.Client") as mock_client:
        # Setup the mock client to simulate successful connection
        instance = mock_client.return_value
        instance.is_connected.return_value = True

        # Setup publish return value
        publish_result = MagicMock()
        publish_result.is_published.return_value = True
        instance.publish.return_value = publish_result

        yield instance


@pytest.fixture
def mock_allowed_users():
    """Mock for allowed users database."""
    with patch("models.get_allowed_users") as mock_get_users:
        allowed_users = {
            "test_user_id": "Test User",
            "Uea6813ef8ec77e7446090621ebcf472a": "Test User 2",
        }
        mock_get_users.return_value = allowed_users
        yield allowed_users


# Constants for testing
PARK_LAT = 24.79155
PARK_LNG = 120.99442
MAX_DIST_KM = 0.5
