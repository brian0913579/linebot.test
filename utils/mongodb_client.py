"""
MongoDB Client Module

This module provides a MongoDB client with connection pooling for user authentication.
It manages the 'authorized_users' collection with user authorization data.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from pymongo import MongoClient, errors
from pymongo.collection import Collection

from utils.logger_config import get_logger

logger = get_logger(__name__)

# Global MongoDB client and database (singleton pattern for connection pooling)
_mongo_client: Optional[MongoClient] = None
_db = None
_users_collection: Optional[Collection] = None


def get_mongo_client() -> MongoClient:
    """
    Get or create MongoDB client with connection pooling.

    Returns:
        MongoClient: MongoDB client instance with connection pool
    """
    global _mongo_client

    if _mongo_client is None:
        from config.secret_manager import get_secret

        mongo_uri = get_secret("MONGO_URI")
        if not mongo_uri:
            raise RuntimeError(
                "MONGO_URI not configured. Please set the MONGO_URI "
                "environment variable or configure it in Google Cloud "
                "Secret Manager."
            )

        try:
            # Create client with connection pooling settings
            _mongo_client = MongoClient(
                mongo_uri,
                maxPoolSize=50,  # Maximum number of connections in the pool
                minPoolSize=10,  # Minimum number of connections in the pool
                maxIdleTimeMS=45000,  # Close connections after 45 seconds of inactivity
                serverSelectionTimeoutMS=5000,  # 5 second timeout for server selection
                connectTimeoutMS=10000,  # 10 second timeout for connection
            )

            # Test the connection
            _mongo_client.admin.command("ping")
            logger.info(
                "MongoDB connection established successfully with connection pooling"
            )

        except errors.ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise RuntimeError(f"MongoDB connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            raise

    return _mongo_client


def get_users_collection() -> Collection:
    """
    Get the authorized_users collection from MongoDB.

    Returns:
        Collection: The authorized_users collection
    """
    global _db, _users_collection

    if _users_collection is None:
        client = get_mongo_client()
        _db = client.get_database()  # Uses the database from the connection URI
        _users_collection = _db["authorized_users"]

        # Create unique index on line_user_id for fast lookups
        try:
            _users_collection.create_index("line_user_id", unique=True)
            logger.info("Ensured unique index on line_user_id field")
        except Exception as e:
            logger.warning(f"Could not create index (may already exist): {e}")

    return _users_collection


def get_allowed_users() -> Dict[str, str]:
    """
    Retrieve all authorized users from MongoDB.

    Returns:
        Dict[str, str]: Dictionary mapping line_user_id to username for authorized users
    """
    try:
        collection = get_users_collection()

        # Query only authorized users
        users = collection.find(
            {"authorized": True}, {"line_user_id": 1, "username": 1, "_id": 0}
        )

        # Convert to dictionary
        allowed_users = {user["line_user_id"]: user["username"] for user in users}

        logger.info(
            f"Successfully retrieved {len(allowed_users)} authorized users from MongoDB"
        )
        return allowed_users

    except Exception as e:
        logger.error(f"Failed to retrieve allowed users from MongoDB: {e}")
        # Return empty dict to fail closed (no users authorized on error)
        return {}


def add_user(line_user_id: str, username: str, authorized: bool = True) -> bool:
    """
    Add a new user to the authorized_users collection.

    Args:
        line_user_id: LINE user ID
        username: Display name for the user
        authorized: Whether the user is authorized (default: True)

    Returns:
        bool: True if user was added successfully, False otherwise
    """
    try:
        collection = get_users_collection()

        user_doc = {
            "line_user_id": line_user_id,
            "username": username,
            "authorized": authorized,
            "added_at": datetime.now(timezone.utc),
        }

        # Insert the user (will fail if user already exists due to unique index)
        result = collection.insert_one(user_doc)

        if result.inserted_id:
            logger.info(
                f"Successfully added user {username} ({line_user_id}) to MongoDB"
            )
            return True
        else:
            logger.error(f"Failed to add user {username} ({line_user_id})")
            return False

    except errors.DuplicateKeyError:
        logger.warning(f"User {line_user_id} already exists in database")
        return False
    except Exception as e:
        logger.error(f"Error adding user to MongoDB: {e}")
        return False


def update_user_authorization(line_user_id: str, authorized: bool) -> bool:
    """
    Update the authorization status of a user.

    Args:
        line_user_id: LINE user ID
        authorized: New authorization status

    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        collection = get_users_collection()

        result = collection.update_one(
            {"line_user_id": line_user_id}, {"$set": {"authorized": authorized}}
        )

        if result.modified_count > 0:
            logger.info(
                f"Updated authorization for user {line_user_id} to {authorized}"
            )
            return True
        else:
            logger.warning(f"No user found with ID {line_user_id} or status unchanged")
            return False

    except Exception as e:
        logger.error(f"Error updating user authorization: {e}")
        return False


def remove_user(line_user_id: str) -> bool:
    """
    Remove a user from the authorized_users collection.

    Args:
        line_user_id: LINE user ID to remove

    Returns:
        bool: True if user was removed successfully, False otherwise
    """
    try:
        collection = get_users_collection()

        result = collection.delete_one({"line_user_id": line_user_id})

        if result.deleted_count > 0:
            logger.info(f"Successfully removed user {line_user_id} from MongoDB")
            return True
        else:
            logger.warning(f"No user found with ID {line_user_id}")
            return False

    except Exception as e:
        logger.error(f"Error removing user from MongoDB: {e}")
        return False


def get_user(line_user_id: str) -> Optional[Dict]:
    """
    Get a specific user from the database.

    Args:
        line_user_id: LINE user ID

    Returns:
        Optional[Dict]: User document if found, None otherwise
    """
    try:
        collection = get_users_collection()
        user = collection.find_one(
            {"line_user_id": line_user_id},
            {"_id": 0},  # Exclude MongoDB's internal _id field
        )

        if user:
            logger.debug(f"Found user {line_user_id} in database")
        else:
            logger.debug(f"User {line_user_id} not found in database")

        return user

    except Exception as e:
        logger.error(f"Error retrieving user from MongoDB: {e}")
        return None


def close_connection():
    """
    Close the MongoDB connection.
    Should be called when the application is shutting down.
    """
    global _mongo_client, _db, _users_collection

    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
        _db = None
        _users_collection = None
        logger.info("MongoDB connection closed")
