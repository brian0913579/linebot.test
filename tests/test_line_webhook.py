import pytest
import json
import base64
import hmac
import hashlib
import time
from unittest.mock import patch, MagicMock
from app import app
from line_webhook import webhook_handler, verify_location_handler, handle_text
from linebot.v3.webhooks import MessageEvent, TextMessageContent, Source

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_line_bot_api():
    with patch('line_webhook.line_bot_api') as mock_api:
        yield mock_api

@pytest.fixture
def mock_handler():
    with patch('line_webhook.handler') as mock_h:
        yield mock_h

# Test webhook handler with invalid signature
def test_webhook_handler_invalid_signature(client):
    """Test webhook handler rejects invalid signatures."""
    with patch('line_webhook.verify_signature', return_value=False):
        response = client.post('/webhook', 
                              headers={'X-Line-Signature': 'invalid_signature'},
                              data='{}')
        assert response.status_code == 400

# Test webhook handler with valid signature
def test_webhook_handler_valid_signature(client, mock_handler):
    """Test webhook handler accepts valid signatures."""
    with patch('line_webhook.verify_signature', return_value=True):
        response = client.post('/webhook', 
                              headers={'X-Line-Signature': 'valid_signature'},
                              data='{}')
        assert response.status_code == 200
        assert mock_handler.handle.called

# Test text message handling for "開關門" command from allowed user
@patch('line_webhook.get_allowed_users')
def test_handle_text_allowed_user(mock_get_allowed_users, mock_line_bot_api):
    """Test handling the '開關門' command from an allowed user."""
    # Setup mock user data
    allowed_user_id = "user123"
    mock_get_allowed_users.return_value = {allowed_user_id: "Test User"}
    
    # Setup authorized user
    with patch('line_webhook.authorized_users', {allowed_user_id: time.time() + 3600}):
        # Create mock event
        event = MagicMock(spec=MessageEvent)
        event.source.user_id = allowed_user_id
        event.message.text = "開關門"
        event.reply_token = "reply123"
        
        # Call handler
        handle_text(event)
        
        # Verify that the reply was sent
        mock_line_bot_api.reply_message.assert_called()

# Test text message handling for non-allowed user
@patch('line_webhook.get_allowed_users')
def test_handle_text_non_allowed_user(mock_get_allowed_users, mock_line_bot_api):
    """Test handling command from a non-allowed user."""
    # Setup mock user data
    allowed_user_id = "user123"
    non_allowed_user_id = "user456"
    mock_get_allowed_users.return_value = {allowed_user_id: "Test User"}
    
    # Create mock event
    event = MagicMock(spec=MessageEvent)
    event.source.user_id = non_allowed_user_id
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
@patch('line_webhook.VERIFY_TOKENS')
@patch('line_webhook.generate_token')
def test_verify_location_valid(mock_generate_token, mock_verify_tokens, client, mock_line_bot_api):
    """Test location verification with valid token and location."""
    # Setup mocks
    test_token = "valid_test_token"
    user_id = "test_user_789"
    expiry = time.time() + 300
    mock_verify_tokens.get.return_value = (user_id, expiry)
    mock_generate_token.return_value = ("open_token_123", "close_token_456")
    
    # Test with valid location
    response = client.post(f'/api/verify-location?token={test_token}', 
                         json={'lat': PARK_LAT, 'lng': PARK_LNG, 'acc': 10})
    
    assert response.status_code == 200
    assert json.loads(response.data)['ok'] == True
    
    # Verify push message was sent
    mock_line_bot_api.push_message.assert_called()

# Constants for testing location verification
PARK_LAT = 24.79155
PARK_LNG = 120.99442