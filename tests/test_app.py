import pytest
import json
import base64
import hmac
import hashlib
import time
from unittest.mock import patch, MagicMock
from app import app
from core.models import get_allowed_users
from core.line_webhook import verify_signature, haversine, VERIFY_TOKENS, authorized_users
from core.token_manager import TOKENS, generate_token, clean_expired_tokens
from config.config_module import PARK_LAT, PARK_LNG, MAX_DIST_KM

# Setup a test client
@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

# Health endpoint test
def test_health_endpoint(client):
    """Test if health check endpoint is responding."""
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.data == b"OK"

# Mock LINE channel secret for testing
@pytest.fixture
def line_channel_secret():
    return "test_channel_secret".encode()

# Mock signature creation for LINE webhook
def create_test_signature(body, secret):
    """Create a test signature for LINE webhook tests."""
    return base64.b64encode(
        hmac.new(
            key=secret,
            msg=body.encode(),
            digestmod=hashlib.sha256
        ).digest()
    ).decode()

# Test signature verification function
def test_verify_signature(line_channel_secret):
    """Test the signature verification for LINE webhook."""
    test_body = '{"test": "data"}'
    correct_signature = create_test_signature(test_body, line_channel_secret)
    
    with patch('core.line_webhook.LINE_CHANNEL_SECRET', line_channel_secret):
        assert verify_signature(correct_signature, test_body) == True
        assert verify_signature("wrong_signature", test_body) == False

# Test haversine distance function
def test_haversine():
    """Test the haversine distance calculation function."""
    # Test with known coordinates and distance
    # Empire State Building to Statue of Liberty is ~8.8 km
    empire_lat, empire_lng = 40.7484, -73.9857
    liberty_lat, liberty_lng = 40.6892, -74.0445
    
    distance = haversine(empire_lat, empire_lng, liberty_lat, liberty_lng)
    assert 8.7 <= distance <= 8.9  # Allow small margin of error
    
    # Test with zero distance (same point)
    assert haversine(PARK_LAT, PARK_LNG, PARK_LAT, PARK_LNG) == 0
    
    # Test with parking lot boundary
    # Point right at MAX_DIST_KM away from the parking lot center
    test_lat = PARK_LAT + (MAX_DIST_KM / 111.32)  # ~1 degree latitude = 111.32 km
    assert haversine(PARK_LAT, PARK_LNG, test_lat, PARK_LNG) - MAX_DIST_KM < 0.01

# Test location verification endpoint
def test_verify_location_endpoint_invalid_token(client):
    """Test location verification with invalid token."""
    response = client.post('/api/verify-location?token=invalid_token', 
                         json={'lat': PARK_LAT, 'lng': PARK_LNG})
    assert response.status_code == 400
    assert json.loads(response.data)['ok'] == False

# Test location verification with valid token but invalid location
@patch('core.line_webhook.VERIFY_TOKENS')
def test_verify_location_endpoint_invalid_location(mock_tokens, client):
    """Test location verification with valid token but location outside range."""
    # Setup mock token
    test_token = "valid_test_token"
    user_id = "test_user_123"
    expiry = time.time() + 300
    mock_tokens.get.return_value = (user_id, expiry)
    
    # Test with location outside allowed radius
    far_lat = PARK_LAT + 1.0  # ~111 km away
    response = client.post(f'/api/verify-location?token={test_token}', 
                         json={'lat': far_lat, 'lng': PARK_LNG})
    assert response.status_code == 200
    assert json.loads(response.data)['ok'] == False

# Test token generation and cleanup
def test_token_generation_and_cleanup():
    """Test token generation and expired token cleanup."""
    # Clear tokens before test
    TOKENS.clear()
    
    user_id = "test_user_456"
    open_token, close_token = generate_token(user_id)
    
    # Verify tokens were stored correctly
    assert open_token in TOKENS
    assert close_token in TOKENS
    
    # Verify token contents
    assert TOKENS[open_token][0] == user_id
    assert TOKENS[open_token][1] == 'open'
    
    assert TOKENS[close_token][0] == user_id
    assert TOKENS[close_token][1] == 'close'
    
    # Set expiry to past time
    TOKENS[open_token] = (user_id, 'open', time.time() - 10)
    
    # Test cleanup
    clean_expired_tokens()
    assert open_token not in TOKENS
    assert close_token in TOKENS

# Mock MQTT client for testing
@pytest.fixture
def mock_mqtt_client():
    with patch('core.mqtt_handler.mqtt.Client') as mock_client:
        # Setup the mock client to simulate successful connection
        instance = mock_client.return_value
        instance.is_connected.return_value = True
        
        # Setup publish return value
        publish_result = MagicMock()
        publish_result.is_published.return_value = True
        instance.publish.return_value = publish_result
        
        yield instance

# Test MQTT handler
@patch('core.mqtt_handler.create_mqtt_client')
def test_mqtt_handler(mock_create_client, mock_mqtt_client):
    """Test the MQTT handler for sending garage commands."""
    from core.mqtt_handler import send_garage_command
    
    # Setup the mock
    mock_create_client.return_value = (mock_mqtt_client, None)
    
    # Test opening command
    success, error = send_garage_command('open')
    assert success is True
    assert error is None
    mock_mqtt_client.publish.assert_called_with('garage/command', 'up', qos=1)
    
    # Test closing command
    success, error = send_garage_command('close')
    assert success is True
    assert error is None
    mock_mqtt_client.publish.assert_called_with('garage/command', 'down', qos=1)

# Test MQTT error handling
@patch('core.mqtt_handler.create_mqtt_client')
def test_mqtt_error_handling(mock_create_client):
    """Test MQTT error handling and retry logic."""
    from core.mqtt_handler import send_garage_command
    
    # Setup the mock to fail connection
    mock_client = MagicMock()
    mock_client.is_connected.return_value = False
    mock_create_client.return_value = (mock_client, None)
    
    # Test with connection timeout
    with patch('core.mqtt_handler.MAX_RETRIES', 1):  # Limit retries for faster test
        with patch('core.mqtt_handler.CONNECT_TIMEOUT', 0.1):  # Short timeout
            success, error = send_garage_command('open')
            assert success is False
            assert "timed out" in error.lower()

# Test rate limiting
@patch('middleware.rate_limiter.limiter')
def test_rate_limiting(mock_limiter):
    """Test rate limiting configuration."""
    from middleware.rate_limiter import configure_limiter, limit_webhook_endpoint
    
    # Create mock app
    mock_app = MagicMock()
    mock_app.view_functions = {"webhook": MagicMock()}
    
    # Test with rate limiting enabled
    with patch('middleware.rate_limiter.RATE_LIMIT_ENABLED', True):
        configure_limiter(mock_app)
        limit_webhook_endpoint(mock_app)
        
        # Verify limiter was initialized and limit was applied
        assert mock_limiter.init_app.called
        assert mock_limiter.limit.called