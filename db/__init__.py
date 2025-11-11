"""
Database package for user authorization.

This package provides a unified interface for user database operations,
supporting both MongoDB Atlas and SQLite with automatic fallback.
"""

from db.database import get_allowed_users, add_user, remove_user, initialize_database

__all__ = ['get_allowed_users', 'add_user', 'remove_user', 'initialize_database']
