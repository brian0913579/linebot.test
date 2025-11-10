"""
Test debug mode functionality with multiple users.
"""
import os
import pytest


def test_debug_user_ids_parsing_single_user():
    """Test that a single debug user ID is parsed correctly."""
    debug_users = "U1234567890abcdef"
    result = debug_users.split(",") if debug_users else []
    assert result == ["U1234567890abcdef"]
    assert len(result) == 1


def test_debug_user_ids_parsing_multiple_users():
    """Test that multiple comma-separated debug user IDs are parsed correctly."""
    debug_users = "U1234567890abcdef,Uanother_user_id,U999888777"
    result = debug_users.split(",") if debug_users else []
    assert result == ["U1234567890abcdef", "Uanother_user_id", "U999888777"]
    assert len(result) == 3


def test_debug_user_ids_parsing_empty():
    """Test that an empty debug user ID string results in an empty list."""
    debug_users = ""
    result = debug_users.split(",") if debug_users else []
    assert result == []
    assert len(result) == 0


def test_debug_user_ids_parsing_with_spaces():
    """Test that debug user IDs with spaces around commas are handled correctly."""
    debug_users = "U1234567890abcdef, Uanother_user_id , U999888777"
    result = [user.strip() for user in debug_users.split(",") if user.strip()] if debug_users else []
    # Spaces should be stripped from each user ID
    assert result == ["U1234567890abcdef", "Uanother_user_id", "U999888777"]
    assert len(result) == 3


def test_debug_user_ids_parsing_with_trailing_comma():
    """Test that trailing commas are handled correctly."""
    debug_users = "U1234567890abcdef,Uanother_user_id,"
    result = [user.strip() for user in debug_users.split(",") if user.strip()] if debug_users else []
    # Empty strings from trailing commas should be filtered out
    assert result == ["U1234567890abcdef", "Uanother_user_id"]
    assert len(result) == 2


def test_debug_user_ids_parsing_only_commas():
    """Test that a string with only commas results in an empty list."""
    debug_users = ",,,"
    result = [user.strip() for user in debug_users.split(",") if user.strip()] if debug_users else []
    assert result == []
    assert len(result) == 0


def test_debug_user_check_single_user():
    """Test that a user in the debug list is correctly identified."""
    DEBUG_MODE = True
    DEBUG_USER_IDS = ["U1234567890abcdef"]
    user_id = "U1234567890abcdef"
    
    is_debug_user = DEBUG_MODE and user_id in DEBUG_USER_IDS
    assert is_debug_user is True


def test_debug_user_check_multiple_users():
    """Test that multiple users in the debug list are correctly identified."""
    DEBUG_MODE = True
    DEBUG_USER_IDS = ["U1234567890abcdef", "Uanother_user_id", "U999888777"]
    
    # Test first user
    is_debug_user = DEBUG_MODE and "U1234567890abcdef" in DEBUG_USER_IDS
    assert is_debug_user is True
    
    # Test second user
    is_debug_user = DEBUG_MODE and "Uanother_user_id" in DEBUG_USER_IDS
    assert is_debug_user is True
    
    # Test third user
    is_debug_user = DEBUG_MODE and "U999888777" in DEBUG_USER_IDS
    assert is_debug_user is True
    
    # Test non-debug user
    is_debug_user = DEBUG_MODE and "U000000000000000" in DEBUG_USER_IDS
    assert is_debug_user is False


def test_debug_mode_disabled():
    """Test that when debug mode is disabled, users are not identified as debug users."""
    DEBUG_MODE = False
    DEBUG_USER_IDS = ["U1234567890abcdef", "Uanother_user_id"]
    user_id = "U1234567890abcdef"
    
    is_debug_user = DEBUG_MODE and user_id in DEBUG_USER_IDS
    assert is_debug_user is False


def test_config_module_integration():
    """Test the actual config module parsing with environment variables."""
    # Set up test environment
    os.environ["DEBUG_MODE"] = "true"
    os.environ["DEBUG_USER_IDS"] = "U111,U222,U333"
    
    # Import config module (this will re-read environment variables)
    from config import config_module
    import importlib
    importlib.reload(config_module)
    
    # Verify the configuration
    assert config_module.DEBUG_MODE is True
    assert len(config_module.DEBUG_USER_IDS) == 3
    assert "U111" in config_module.DEBUG_USER_IDS
    assert "U222" in config_module.DEBUG_USER_IDS
    assert "U333" in config_module.DEBUG_USER_IDS
    
    # Clean up
    del os.environ["DEBUG_MODE"]
    del os.environ["DEBUG_USER_IDS"]
