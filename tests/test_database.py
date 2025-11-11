"""
Tests for the database abstraction layer.
"""

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

# Set test environment before importing database module
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")
os.environ.pop("MONGO_URI", None)  # Ensure no MongoDB connection in tests
os.environ["DB_MODE"] = "sqlite"

from db.database import (
    initialize_database,
    get_allowed_users,
    add_user,
    remove_user,
    close_connections,
)


@pytest.fixture
def clean_database():
    """Create a clean database for each test."""
    # Create temporary database file
    db_path = tempfile.mktemp(suffix=".db")
    old_db_path = os.environ.get("DB_PATH")
    os.environ["DB_PATH"] = db_path
    
    # Reset global state
    from db import database as db_module
    db_module._mongo_client = None
    db_module._mongo_collection = None
    db_module._database_mode = None
    
    # Initialize database
    initialize_database()
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Reset global state again
    db_module._mongo_client = None
    db_module._mongo_collection = None
    db_module._database_mode = None
    
    # Restore old DB_PATH
    if old_db_path:
        os.environ["DB_PATH"] = old_db_path
    
    close_connections()


def test_initialize_database_sqlite(clean_database):
    """Test database initialization with SQLite."""
    mode = initialize_database()
    assert mode == "sqlite"


def test_get_allowed_users_empty(clean_database):
    """Test getting users from an empty database."""
    users = get_allowed_users()
    assert isinstance(users, dict)
    assert len(users) == 0


def test_add_user_sqlite(clean_database):
    """Test adding a user to SQLite."""
    success, message = add_user("Utest123", "Test User")
    assert success is True
    assert "added" in message.lower() or "sqlite" in message.lower()
    
    # Verify user was added
    users = get_allowed_users()
    assert "Utest123" in users
    assert users["Utest123"] == "Test User"


def test_add_multiple_users(clean_database):
    """Test adding multiple users."""
    add_user("Uuser1", "User One")
    add_user("Uuser2", "User Two")
    add_user("Uuser3", "User Three")
    
    users = get_allowed_users()
    assert len(users) == 3
    assert "Uuser1" in users
    assert "Uuser2" in users
    assert "Uuser3" in users


def test_add_duplicate_user(clean_database):
    """Test adding a user that already exists."""
    # Add user first time
    add_user("Utest456", "Original Name")
    
    # Add same user with different name (should update)
    success, message = add_user("Utest456", "Updated Name")
    assert success is True
    
    # Verify user was updated
    users = get_allowed_users()
    assert users["Utest456"] == "Updated Name"


def test_remove_user(clean_database):
    """Test removing a user."""
    # Add a user
    add_user("Utest789", "Test User")
    
    # Verify user exists
    users = get_allowed_users()
    assert "Utest789" in users
    
    # Remove user
    success, message = remove_user("Utest789")
    assert success is True
    assert "deauthorized" in message.lower() or "removed" in message.lower()
    
    # Verify user was removed
    users = get_allowed_users()
    assert "Utest789" not in users


def test_remove_nonexistent_user(clean_database):
    """Test removing a user that doesn't exist."""
    success, message = remove_user("Unonexistent")
    assert success is False
    assert "not found" in message.lower()


def test_user_authorization_workflow(clean_database):
    """Test complete user authorization workflow."""
    # Start with empty database
    users = get_allowed_users()
    assert len(users) == 0
    
    # Add user
    add_user("Uworkflow", "Workflow User")
    users = get_allowed_users()
    assert len(users) == 1
    assert "Uworkflow" in users
    
    # Remove user
    remove_user("Uworkflow")
    users = get_allowed_users()
    assert len(users) == 0


def test_parameterized_queries(clean_database):
    """Test that special characters are handled safely (SQL injection protection)."""
    # Add user with special characters in name
    special_name = "User'; DROP TABLE allowed_users; --"
    success, message = add_user("Usafe123", special_name)
    assert success is True
    
    # Verify user was added safely
    users = get_allowed_users()
    assert "Usafe123" in users
    assert users["Usafe123"] == special_name


@pytest.mark.database
def test_mongodb_fallback_to_sqlite():
    """Test automatic fallback from MongoDB to SQLite."""
    # Set invalid MongoDB URI
    os.environ["MONGO_URI"] = "mongodb://invalid:27017"
    os.environ["DB_MODE"] = "mongo"
    
    # Create temporary database for this test
    db_path = tempfile.mktemp(suffix=".db")
    os.environ["DB_PATH"] = db_path
    
    # Reset database state
    from db import database as db_module
    db_module._mongo_client = None
    db_module._mongo_collection = None
    db_module._database_mode = None
    
    try:
        # Initialize database - should fall back to SQLite
        mode = initialize_database()
        # MongoDB connection will fail and fall back to SQLite
        assert mode in ["mongo", "sqlite"]  # May fall back to sqlite
        
        # Verify we can still add users
        success, message = add_user("Ufallback", "Fallback User")
        assert success is True
        
        # Verify we can retrieve users
        users = get_allowed_users()
        assert "Ufallback" in users
        
    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.remove(db_path)
        os.environ.pop("MONGO_URI", None)
        os.environ["DB_MODE"] = "sqlite"
        close_connections()


def test_close_connections():
    """Test closing database connections."""
    # This should not raise any errors
    close_connections()
    
    # After closing, we should be able to reinitialize
    mode = initialize_database()
    assert mode in ["mongo", "sqlite"]
