import pytest
import time
from unittest.mock import patch
from token_manager import generate_token, clean_expired_tokens, TOKENS

@pytest.fixture
def clear_tokens():
    """Fixture to clear tokens before and after tests."""
    TOKENS.clear()
    yield
    TOKENS.clear()

def test_generate_token(clear_tokens):
    """Test token generation creates unique tokens."""
    user_id = "test_user_123"
    
    # Generate tokens
    open_token, close_token = generate_token(user_id)
    
    # Verify tokens are different
    assert open_token != close_token
    
    # Verify tokens have correct length
    assert len(open_token) > 10
    assert len(close_token) > 10
    
    # Verify tokens were stored in TOKENS
    assert open_token in TOKENS
    assert close_token in TOKENS
    
    # Verify token content
    user_id_open, action_open, expiry_open = TOKENS[open_token]
    user_id_close, action_close, expiry_close = TOKENS[close_token]
    
    assert user_id_open == user_id
    assert user_id_close == user_id
    assert action_open == 'open'
    assert action_close == 'close'
    
    # Verify expiry time is in the future (300 seconds)
    now = time.time()
    assert expiry_open > now
    assert expiry_close > now
    assert expiry_open - now <= 300
    assert expiry_close - now <= 300

def test_clean_expired_tokens(clear_tokens):
    """Test cleaning of expired tokens."""
    # Create mix of expired and valid tokens
    now = time.time()
    
    # Valid tokens (5 minutes in the future)
    TOKENS['valid1'] = ('user1', 'open', now + 300)
    TOKENS['valid2'] = ('user2', 'close', now + 300)
    
    # Expired tokens (in the past)
    TOKENS['expired1'] = ('user3', 'open', now - 10)
    TOKENS['expired2'] = ('user4', 'close', now - 100)
    
    # Borderline token (just expired)
    TOKENS['expired3'] = ('user5', 'open', now - 0.1)
    
    # Run cleanup
    clean_expired_tokens()
    
    # Verify only valid tokens remain
    assert 'valid1' in TOKENS
    assert 'valid2' in TOKENS
    assert 'expired1' not in TOKENS
    assert 'expired2' not in TOKENS
    assert 'expired3' not in TOKENS
    assert len(TOKENS) == 2

def test_generate_token_multiple_users(clear_tokens):
    """Test token generation for multiple users."""
    user1 = "user_abc"
    user2 = "user_xyz"
    
    # Generate tokens for both users
    open1, close1 = generate_token(user1)
    open2, close2 = generate_token(user2)
    
    # Verify all tokens are unique
    tokens = [open1, close1, open2, close2]
    assert len(tokens) == len(set(tokens))
    
    # Verify user IDs are correctly associated
    assert TOKENS[open1][0] == user1
    assert TOKENS[close1][0] == user1
    assert TOKENS[open2][0] == user2
    assert TOKENS[close2][0] == user2

def test_token_expiry_values(clear_tokens):
    """Test that token expiry is set to 5 minutes in the future."""
    # Generate token
    user_id = "expiry_test_user"
    open_token, _ = generate_token(user_id)
    
    # Get token expiry
    _, _, expiry = TOKENS[open_token]
    
    # Verify expiry time (allow small margin for test execution time)
    expected_expiry = time.time() + 300
    assert abs(expiry - expected_expiry) < 1