"""
Database abstraction layer for user authorization.

This module provides a unified interface for MongoDB Atlas (primary) and SQLite (fallback)
database operations. It automatically handles connection failures and fallback scenarios.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from pymongo import MongoClient, errors as mongo_errors
from pymongo.collection import Collection

from utils.logger_config import get_logger

logger = get_logger(__name__)

# Database configuration
def _get_mongo_uri():
    """Get MongoDB URI from environment."""
    return os.environ.get("MONGO_URI", None)

def _get_db_mode():
    """Get database mode from environment."""
    return os.environ.get("DB_MODE", "mongo").lower()

def _get_db_path():
    """Get SQLite database path from environment."""
    return os.environ.get("DB_PATH", "/tmp/users.db")

# Global database state
_mongo_client: Optional[MongoClient] = None
_mongo_collection: Optional[Collection] = None
_database_mode: Optional[str] = None


def _get_mongo_collection() -> Optional[Collection]:
    """
    Get or create MongoDB collection.
    
    Returns:
        MongoDB collection if successful, None otherwise.
    """
    global _mongo_client, _mongo_collection
    
    if _mongo_collection is not None:
        return _mongo_collection
    
    mongo_uri = _get_mongo_uri()
    if not mongo_uri:
        logger.warning("MONGO_URI not set, MongoDB unavailable")
        return None
    
    try:
        # Create MongoDB client with timeout
        _mongo_client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000
        )
        
        # Test connection
        _mongo_client.admin.command('ping')
        
        # Get database and collection
        db = _mongo_client['linebot_garage']
        _mongo_collection = db['authorized_users']
        
        # Create unique index on line_user_id
        _mongo_collection.create_index("line_user_id", unique=True)
        
        logger.info("Successfully connected to MongoDB Atlas")
        return _mongo_collection
        
    except (mongo_errors.ConnectionFailure, 
            mongo_errors.ServerSelectionTimeoutError,
            mongo_errors.ConfigurationError) as e:
        logger.error(f"MongoDB connection failed: {e}")
        _mongo_client = None
        _mongo_collection = None
        return None
    except Exception as e:
        logger.error(f"Unexpected error connecting to MongoDB: {e}")
        _mongo_client = None
        _mongo_collection = None
        return None


def _init_sqlite_db() -> None:
    """
    Initialize SQLite database with the allowed_users table.
    """
    db_path = _get_db_path()
    try:
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS allowed_users (
                user_id TEXT PRIMARY KEY,
                user_name TEXT,
                authorized INTEGER DEFAULT 1,
                added_at TEXT
            )
            """
        )
        connection.commit()
        connection.close()
        logger.info(f"SQLite database initialized at {db_path}")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")
        raise


def _get_current_mode() -> str:
    """
    Determine the current database mode.
    
    Returns:
        'mongo' if MongoDB is available, 'sqlite' otherwise.
    """
    global _database_mode
    
    # Return cached mode if available
    if _database_mode:
        return _database_mode
    
    db_mode = _get_db_mode()
    mongo_uri = _get_mongo_uri()
    
    # Try MongoDB first if configured
    if db_mode == "mongo" or (db_mode == "auto" and mongo_uri):
        collection = _get_mongo_collection()
        if collection is not None:
            _database_mode = "mongo"
            logger.info("Using MongoDB as primary database")
            return "mongo"
    
    # Fall back to SQLite
    _database_mode = "sqlite"
    logger.info("Using SQLite as database (MongoDB unavailable or not configured)")
    _init_sqlite_db()
    return "sqlite"


def initialize_database() -> str:
    """
    Initialize the database connection and return the active mode.
    
    Returns:
        'mongo' or 'sqlite' depending on what's available.
    """
    return _get_current_mode()


def get_allowed_users() -> Dict[str, str]:
    """
    Get all allowed users from the database.
    
    Returns:
        Dictionary mapping user_id to username.
    """
    mode = _get_current_mode()
    
    if mode == "mongo":
        try:
            collection = _get_mongo_collection()
            if collection is not None:
                # Query MongoDB for authorized users
                users = collection.find({"authorized": True})
                result = {user["line_user_id"]: user["username"] for user in users}
                logger.debug(f"Retrieved {len(result)} users from MongoDB")
                return result
        except Exception as e:
            logger.error(f"Error retrieving users from MongoDB: {e}")
            logger.warning("Falling back to SQLite for user retrieval")
            # Fall through to SQLite
    
    # SQLite fallback
    try:
        db_path = _get_db_path()
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        cursor.execute(
            "SELECT user_id, user_name FROM allowed_users WHERE authorized = 1"
        )
        users = cursor.fetchall()
        connection.close()
        result = {user[0]: user[1] for user in users}
        logger.debug(f"Retrieved {len(result)} users from SQLite")
        return result
    except Exception as e:
        logger.error(f"Error retrieving users from SQLite: {e}")
        return {}


def add_user(user_id: str, username: str) -> Tuple[bool, str]:
    """
    Add a new authorized user to the database.
    
    Args:
        user_id: LINE user ID
        username: Display name for the user
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    mode = _get_current_mode()
    
    if mode == "mongo":
        try:
            collection = _get_mongo_collection()
            if collection is not None:
                # Prepare user document
                user_doc = {
                    "line_user_id": user_id,
                    "username": username,
                    "authorized": True,
                    "added_at": datetime.now(timezone.utc)
                }
                
                # Insert or update user
                collection.update_one(
                    {"line_user_id": user_id},
                    {"$set": user_doc},
                    upsert=True
                )
                
                logger.info(f"Successfully added user {user_id} ({username}) to MongoDB")
                return True, f"User {username} added to MongoDB"
        except mongo_errors.DuplicateKeyError:
            logger.warning(f"User {user_id} already exists in MongoDB")
            return False, f"User {user_id} already exists"
        except Exception as e:
            logger.error(f"Error adding user to MongoDB: {e}")
            logger.warning("Falling back to SQLite for user addition")
            # Fall through to SQLite
    
    # SQLite fallback
    try:
        db_path = _get_db_path()
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Check if user exists
        cursor.execute("SELECT user_id FROM allowed_users WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing user
            cursor.execute(
                """
                UPDATE allowed_users 
                SET user_name = ?, authorized = 1, added_at = ?
                WHERE user_id = ?
                """,
                (username, datetime.now(timezone.utc).isoformat(), user_id)
            )
            logger.info(f"Updated existing user {user_id} ({username}) in SQLite")
        else:
            # Insert new user
            cursor.execute(
                """
                INSERT INTO allowed_users (user_id, user_name, authorized, added_at)
                VALUES (?, ?, 1, ?)
                """,
                (user_id, username, datetime.now(timezone.utc).isoformat())
            )
            logger.info(f"Successfully added user {user_id} ({username}) to SQLite")
        
        connection.commit()
        connection.close()
        return True, f"User {username} added to SQLite"
        
    except Exception as e:
        logger.error(f"Error adding user to SQLite: {e}")
        return False, f"Failed to add user: {str(e)}"


def remove_user(user_id: str) -> Tuple[bool, str]:
    """
    Remove or deauthorize a user from the database.
    
    Args:
        user_id: LINE user ID to remove
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    mode = _get_current_mode()
    
    if mode == "mongo":
        try:
            collection = _get_mongo_collection()
            if collection is not None:
                # Set authorized to False instead of deleting
                result = collection.update_one(
                    {"line_user_id": user_id},
                    {"$set": {"authorized": False}}
                )
                
                if result.modified_count > 0:
                    logger.info(f"Successfully deauthorized user {user_id} in MongoDB")
                    return True, f"User {user_id} deauthorized in MongoDB"
                else:
                    logger.warning(f"User {user_id} not found in MongoDB")
                    return False, f"User {user_id} not found"
        except Exception as e:
            logger.error(f"Error removing user from MongoDB: {e}")
            logger.warning("Falling back to SQLite for user removal")
            # Fall through to SQLite
    
    # SQLite fallback
    try:
        db_path = _get_db_path()
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Set authorized to 0 instead of deleting
        cursor.execute(
            "UPDATE allowed_users SET authorized = 0 WHERE user_id = ?",
            (user_id,)
        )
        
        if cursor.rowcount > 0:
            logger.info(f"Successfully deauthorized user {user_id} in SQLite")
            connection.commit()
            connection.close()
            return True, f"User {user_id} deauthorized in SQLite"
        else:
            logger.warning(f"User {user_id} not found in SQLite")
            connection.close()
            return False, f"User {user_id} not found"
            
    except Exception as e:
        logger.error(f"Error removing user from SQLite: {e}")
        return False, f"Failed to remove user: {str(e)}"


def close_connections() -> None:
    """
    Close all database connections.
    Should be called on application shutdown.
    """
    global _mongo_client, _mongo_collection, _database_mode
    
    if _mongo_client is not None:
        try:
            _mongo_client.close()
            logger.info("MongoDB connection closed")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
    
    _mongo_client = None
    _mongo_collection = None
    _database_mode = None
