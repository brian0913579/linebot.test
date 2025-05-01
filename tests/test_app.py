import pytest
from app import app  # Import your Flask app
from flask import json

# Setup a test client
@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

# Test if the app is up and running
def test_app_is_up(client):
    """Test if the app is running."""
    response = client.get('/')
    assert response.status_code == 200

# Test user authentication for an allowed user
def test_user_authentication(client):
    """Test user authentication for an allowed user."""
    allowed_user_id = 'Uea6813ef8ec77e7446090621ebcf472a'  # Replace with an allowed user ID
    response = client.post('/some-endpoint', json={'user_id': allowed_user_id})
    assert response.status_code == 200
    assert b"Authorized" in response.data

# Test user authentication for a non-allowed user
def test_user_not_authenticated(client):
    """Test that an unauthorized user gets a rejection message."""
    non_allowed_user_id = 'UnauthorizedUserID'
    response = client.post('/some-endpoint', json={'user_id': non_allowed_user_id})
    assert response.status_code == 403  # Forbidden
    assert b"Unauthorized" in response.data

# Test the location-based functionality
def test_location_check(client):
    """Test if the location check for the parking lot works."""
    test_data = {
        'latitude': 24.79155,
        'longitude': 120.99442
    }
    response = client.post('/check-location', json=test_data)
    assert response.status_code == 200
    response_json = json.loads(response.data)
    assert response_json["message"] == "Inside parking lot"

# Test the response when an invalid location is sent
def test_invalid_location(client):
    """Test if invalid locations are handled properly."""
    invalid_data = {
        'latitude': 0.0,
        'longitude': 0.0
    }
    response = client.post('/check-location', json=invalid_data)
    assert response.status_code == 400  # Bad request
    response_json = json.loads(response.data)
    assert response_json["error"] == "Invalid location"

# Test token-based functionality for opening the gate
def test_open_gate(client):
    """Test the gate opening functionality using a valid token."""
    valid_token = 'ValidToken123'
    response = client.post('/open-gate', json={'token': valid_token})
    assert response.status_code == 200
    response_json = json.loads(response.data)
    assert response_json["message"] == "Gate opened"

# Test token-based functionality for closing the gate
def test_close_gate(client):
    """Test the gate closing functionality using a valid token."""
    valid_token = 'ValidToken123'
    response = client.post('/close-gate', json={'token': valid_token})
    assert response.status_code == 200
    response_json = json.loads(response.data)
    assert response_json["message"] == "Gate closed"