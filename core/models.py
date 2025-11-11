"""
User Models Module

This module provides functions for retrieving user authorization data from MongoDB.
"""

from utils.mongodb_client import get_allowed_users

# Re-export get_allowed_users for backward compatibility
__all__ = ["get_allowed_users"]
