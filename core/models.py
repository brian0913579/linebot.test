"""
User authorization models.

This module provides user authorization functions using the database abstraction layer.
"""

from db.database import get_allowed_users as db_get_allowed_users


def get_allowed_users():
    """
    Get all allowed users from the database.

    Returns:
        Dictionary mapping user_id to username.
    """
    return db_get_allowed_users()
