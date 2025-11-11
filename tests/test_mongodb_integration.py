"""
Test MongoDB integration for user authentication.

These tests verify that the MongoDB client module works correctly.
Note: These tests require a MongoDB connection to be configured.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch


class TestMongoDBClient:
    """Test suite for MongoDB client functionality."""

    def test_get_allowed_users_empty(self):
        """Test get_allowed_users returns empty dict when no users exist."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock empty result
            mock_collection.return_value.find.return_value = []

            from utils.mongodb_client import get_allowed_users

            result = get_allowed_users()

            assert result == {}
            mock_collection.return_value.find.assert_called_once()

    def test_get_allowed_users_with_users(self):
        """Test get_allowed_users returns dict of authorized users."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock user data
            mock_users = [
                {"line_user_id": "U123", "username": "User1"},
                {"line_user_id": "U456", "username": "User2"},
            ]
            mock_collection.return_value.find.return_value = mock_users

            from utils.mongodb_client import get_allowed_users

            result = get_allowed_users()

            assert result == {"U123": "User1", "U456": "User2"}
            assert len(result) == 2

    def test_get_allowed_users_handles_exception(self):
        """Test get_allowed_users returns empty dict on error."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock exception
            mock_collection.return_value.find.side_effect = Exception(
                "Connection error"
            )

            from utils.mongodb_client import get_allowed_users

            result = get_allowed_users()

            # Should return empty dict on error (fail closed)
            assert result == {}

    def test_add_user_success(self):
        """Test add_user successfully adds a user."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock successful insert
            mock_result = Mock()
            mock_result.inserted_id = "mock_id"
            mock_collection.return_value.insert_one.return_value = mock_result

            from utils.mongodb_client import add_user

            result = add_user("U789", "TestUser", authorized=True)

            assert result is True
            mock_collection.return_value.insert_one.assert_called_once()

            # Verify the document structure
            call_args = mock_collection.return_value.insert_one.call_args
            doc = call_args[0][0]
            assert doc["line_user_id"] == "U789"
            assert doc["username"] == "TestUser"
            assert doc["authorized"] is True
            assert "added_at" in doc

    def test_add_user_duplicate(self):
        """Test add_user handles duplicate user IDs."""
        from pymongo import errors

        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock duplicate key error
            mock_collection.return_value.insert_one.side_effect = (
                errors.DuplicateKeyError("Duplicate")
            )

            from utils.mongodb_client import add_user

            result = add_user("U789", "TestUser")

            assert result is False

    def test_update_user_authorization_success(self):
        """Test update_user_authorization successfully updates status."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock successful update
            mock_result = Mock()
            mock_result.modified_count = 1
            mock_collection.return_value.update_one.return_value = mock_result

            from utils.mongodb_client import update_user_authorization

            result = update_user_authorization("U789", False)

            assert result is True
            mock_collection.return_value.update_one.assert_called_once_with(
                {"line_user_id": "U789"}, {"$set": {"authorized": False}}
            )

    def test_update_user_authorization_not_found(self):
        """Test update_user_authorization when user doesn't exist."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock no documents modified
            mock_result = Mock()
            mock_result.modified_count = 0
            mock_collection.return_value.update_one.return_value = mock_result

            from utils.mongodb_client import update_user_authorization

            result = update_user_authorization("U999", True)

            assert result is False

    def test_remove_user_success(self):
        """Test remove_user successfully removes a user."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock successful deletion
            mock_result = Mock()
            mock_result.deleted_count = 1
            mock_collection.return_value.delete_one.return_value = mock_result

            from utils.mongodb_client import remove_user

            result = remove_user("U789")

            assert result is True
            mock_collection.return_value.delete_one.assert_called_once_with(
                {"line_user_id": "U789"}
            )

    def test_remove_user_not_found(self):
        """Test remove_user when user doesn't exist."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock no documents deleted
            mock_result = Mock()
            mock_result.deleted_count = 0
            mock_collection.return_value.delete_one.return_value = mock_result

            from utils.mongodb_client import remove_user

            result = remove_user("U999")

            assert result is False

    def test_get_user_found(self):
        """Test get_user returns user data when found."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock user data
            mock_user = {
                "line_user_id": "U123",
                "username": "TestUser",
                "authorized": True,
                "added_at": datetime.now(timezone.utc),
            }
            mock_collection.return_value.find_one.return_value = mock_user

            from utils.mongodb_client import get_user

            result = get_user("U123")

            assert result == mock_user
            assert result["username"] == "TestUser"

    def test_get_user_not_found(self):
        """Test get_user returns None when user doesn't exist."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock no user found
            mock_collection.return_value.find_one.return_value = None

            from utils.mongodb_client import get_user

            result = get_user("U999")

            assert result is None


class TestModelsIntegration:
    """Test that core/models.py correctly uses MongoDB client."""

    def test_models_get_allowed_users(self):
        """Test that models.get_allowed_users uses MongoDB."""
        with patch("utils.mongodb_client.get_users_collection") as mock_collection:
            # Mock user data
            mock_users = [
                {"line_user_id": "U111", "username": "Alice"},
                {"line_user_id": "U222", "username": "Bob"},
            ]
            mock_collection.return_value.find.return_value = mock_users

            from core.models import get_allowed_users

            result = get_allowed_users()

            assert result == {"U111": "Alice", "U222": "Bob"}


class TestConnectionPooling:
    """Test MongoDB connection pooling functionality."""

    def test_get_mongo_client_singleton(self):
        """Test that get_mongo_client returns the same instance."""
        with patch("utils.mongodb_client.MongoClient") as mock_mongo:
            with patch("config.secret_manager.get_secret") as mock_secret:
                mock_secret.return_value = "mongodb://localhost:27017/test"
                mock_client = MagicMock()
                mock_mongo.return_value = mock_client

                from utils.mongodb_client import get_mongo_client

                # Reset the global client
                import utils.mongodb_client

                utils.mongodb_client._mongo_client = None

                # First and second calls
                get_mongo_client()
                get_mongo_client()

                # Should only create client once
                assert mock_mongo.call_count == 1

    def test_get_mongo_client_connection_settings(self):
        """Test that connection pooling settings are correct."""
        with patch("utils.mongodb_client.MongoClient") as mock_mongo:
            with patch("config.secret_manager.get_secret") as mock_secret:
                mock_secret.return_value = "mongodb://localhost:27017/test"
                mock_client = MagicMock()
                mock_mongo.return_value = mock_client

                from utils.mongodb_client import get_mongo_client

                # Reset the global client
                import utils.mongodb_client

                utils.mongodb_client._mongo_client = None

                get_mongo_client()

                # Verify connection settings
                call_kwargs = mock_mongo.call_args[1]
                assert call_kwargs["maxPoolSize"] == 50
                assert call_kwargs["minPoolSize"] == 10
                assert call_kwargs["maxIdleTimeMS"] == 45000
                assert call_kwargs["serverSelectionTimeoutMS"] == 5000

    def test_get_mongo_client_no_uri(self):
        """Test that get_mongo_client raises error when MONGO_URI not set."""
        with patch("config.secret_manager.get_secret") as mock_secret:
            mock_secret.return_value = None

            from utils.mongodb_client import get_mongo_client

            # Reset the global client
            import utils.mongodb_client

            utils.mongodb_client._mongo_client = None

            with pytest.raises(RuntimeError, match="MONGO_URI not configured"):
                get_mongo_client()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
