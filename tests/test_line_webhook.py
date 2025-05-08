import pytest
import json
import base64
import hmac
import hashlib
import time
from unittest.mock import patch, MagicMock
from app import app
from core.line_webhook import webhook_handler, verify_location_handler, handle_text
from linebot.v3.webhooks import MessageEvent, TextMessageContent, Source
from linebot.v3.messaging import (
    TextMessage,
    TemplateMessage,
    ButtonsTemplate,
    PostbackAction
)
@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_line_bot_api():
    with patch('core.line_webhook.line_bot_api') as mock_api:
        yield mock_api

@pytest.fixture
def mock_handler():
    with patch('core.line_webhook.handler') as mock_h:
        yield mock_h

# Test webhook handler with invalid signature
def test_webhook_handler_invalid_signature(client):
    """Test webhook handler rejects invalid signatures."""
    with patch('core.line_webhook.verify_signature', return_value=False):
        response = client.post('/webhook', 
                              headers={'X-Line-Signature': 'invalid_signature'},
                              data='{}')
        assert response.status_code == 400

# Test webhook handler with valid signature
def webhook_handler():
    """
    Handle incoming webhook events from LINE Platform.
    """
    body = request.get_data(as_text=True)
    signature = request.headers.get('X-Line-Signature', '')

    if not verify_signature(signature, body):
        abort(400, description="Invalid signature")

    try:
        handler.handle(body, signature)
        logger.info("Webhook processed successfully")
        return 'OK', 200
    except InvalidSignatureError:
        logger.error("Invalid signature from LINE Platform")
        abort(400, description="Invalid signature")
    except Exception as e:
        logger.error(f"Error while handling webhook: {e}")
        logger.error(f"Request body: {body[:200]}...")
        return 'OK', 200  # Still return 200 to acknowledge receipt

# Test text message handling for "開關門" command from allowed user
@patch('core.line_webhook.get_allowed_users')
@patch('core.line_webhook.line_bot_api')
def test_handle_text_allowed_user(mock_line_bot_api, mock_get_allowed_users):
    """Test handling the '開關門' command from an allowed user."""
    # Setup mock user data
    allowed_user_id = "user123"
    mock_get_allowed_users.return_value = {allowed_user_id: "Test User"}
    
    # Setup authorized user
    with patch('core.line_webhook.authorized_users', {allowed_user_id: time.time() + 3600}):
        # Create mock event
        source = Source(type="user", user_id=allowed_user_id)
        message = TextMessageContent(
            id="message123",
            text="開關門",
            quoteToken="quote_token_123"
        )
        event = MessageEvent(
            type="message",
            mode="active",
            timestamp=int(time.time() * 1000),
            source=source,
            message=message,
            reply_token="reply123",
            webhook_event_id="webhook_event_123",
            delivery_context={"isRedelivery": False}
        )
        
        # Call handler
        handle_text(event)
        
        # Verify reply was sent
        mock_line_bot_api.reply_message.assert_called_once()
        args = mock_line_bot_api.reply_message.call_args[0]
        assert args[0].reply_token == "reply123"
        assert len(args[1]) == 1  # Ensure only one message is sent
        
        # Check that we got a TemplateMessage with ButtonsTemplate
        message = args[1][0]
        assert isinstance(message, TemplateMessage)
        assert message.alt_text == '開關門選單'
        assert isinstance(message.template, ButtonsTemplate)
        assert len(message.template.actions) == 2
        assert message.template.actions[0].label == '開門'
        assert message.template.actions[1].label == '關門'
# Test text message handling for non-allowed user
@patch('core.line_webhook.get_allowed_users')
@patch('core.line_webhook.line_bot_api')
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
@patch('core.line_webhook.VERIFY_TOKENS')
@patch('core.line_webhook.generate_token')
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