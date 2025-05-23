import json
import time
from unittest.mock import MagicMock, patch

import pytest
from linebot.v3.webhooks import MessageEvent

from app import app
from core.line_webhook import handle_text


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_line_bot_api():
    with patch("core.line_webhook.line_bot_api") as mock_api:
        yield mock_api


@pytest.fixture
def mock_handler():
    with patch("core.line_webhook.handler") as mock_h:
        yield mock_h


# Test webhook handler with invalid signature
def test_webhook_handler_invalid_signature(client):
    """Test webhook handler rejects invalid signatures."""
    with patch("core.line_webhook.verify_signature", return_value=False):
        response = client.post(
            "/webhook", headers={"X-Line-Signature": "invalid_signature"}, data="{}"
        )
        assert response.status_code == 400


# Test text message handling for non-allowed user
@patch("core.line_webhook.get_allowed_users")
@patch("core.line_webhook.line_bot_api")
def test_handle_text_non_allowed_user(mock_line_bot_api, mock_get_allowed_users):
    """Test handling command from a non-allowed user."""
    # Setup mock user data
    allowed_user_id = "user123"
    non_allowed_user_id = "user456"
    mock_get_allowed_users.return_value = {allowed_user_id: "Test User"}

    # Create mock event
    event = MagicMock(spec=MessageEvent)
    event.source = MagicMock()  # Explicitly mock the source attribute
    event.source.user_id = non_allowed_user_id
    event.message = MagicMock()  # Explicitly mock the message attribute
    event.message.text = "開關門"
    event.reply_token = "reply123"

    # Call handler
    handle_text(event)

    # Verify that an error message was sent
    mock_line_bot_api.reply_message.assert_called()
    # Check that the rejection message was included
    args = mock_line_bot_api.reply_message.call_args[0]
    assert "未註冊" in str(args) or "尚未註冊" in str(args)


# Test location verification with valid token and location
@patch("core.line_webhook.VERIFY_TOKENS")
@patch("core.line_webhook.generate_token")
def test_verify_location_valid(
    mock_generate_token, mock_verify_tokens, client, mock_line_bot_api
):
    """Test location verification with valid token and location."""
    # Setup mocks
    test_token = "valid_test_token"
    user_id = "test_user_789"
    expiry = time.time() + 300
    mock_verify_tokens.get.return_value = (user_id, expiry)
    mock_generate_token.return_value = ("open_token_123", "close_token_456")

    # Test with valid location
    response = client.post(
        f"/api/verify-location?token={test_token}",
        json={"lat": PARK_LAT, "lng": PARK_LNG, "acc": 10},
    )

    assert response.status_code == 200
    assert json.loads(response.data)["ok"] is True

    # Verify push message was sent
    mock_line_bot_api.push_message.assert_called()


# Constants for testing location verification
PARK_LAT = 24.79155
PARK_LNG = 120.99442
