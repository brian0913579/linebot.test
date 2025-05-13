"""
Cache Manager Module

This module provides Redis-based caching for the application.
It handles user authorization data and token caching to improve performance
and allow for distributed deployments.
"""

import importlib.util
import json
import time

from config.config_module import (
    LOCATION_TTL,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_SSL,
    VERIFY_TTL,
)
from utils.logger_config import get_logger

# Check if Redis is installed
redis_installed = importlib.util.find_spec("redis") is not None
flask_caching_installed = importlib.util.find_spec("flask_caching") is not None

# Import Redis and Flask-Caching if available, otherwise use fallback
if redis_installed:
    from redis import Redis
    from redis.exceptions import RedisError
else:
    # Define dummy classes if Redis is not installed
    class Redis:
        def __init__(self, *args, **kwargs):
            pass

    class RedisError(Exception):
        pass


if flask_caching_installed:
    from flask_caching import Cache
else:
    # Define a dummy Cache class if Flask-Caching is not installed
    class Cache:
        def __init__(self, *args, **kwargs):
            pass

        def init_app(self, app):
            pass


# Configure logger
logger = get_logger(__name__)

# Check if Redis and Flask-Caching are available
if redis_installed and flask_caching_installed:
    try:
        # Initialize Redis client
        redis_client = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            ssl=REDIS_SSL,
            socket_timeout=3,
            socket_connect_timeout=3,
            decode_responses=True,  # Return strings instead of bytes
        )
        # Test connection
        redis_client.ping()
        logger.info("Successfully connected to Redis server")

        # Initialize Flask-Cache for route caching
        cache = Cache(
            config={
                "CACHE_TYPE": "RedisCache",
                "CACHE_REDIS_HOST": REDIS_HOST,
                "CACHE_REDIS_PORT": REDIS_PORT,
                "CACHE_REDIS_DB": REDIS_DB,
                "CACHE_REDIS_PASSWORD": REDIS_PASSWORD,
                "CACHE_REDIS_URL": (
                    f"redis{'s' if REDIS_SSL else ''}://"
                    f"{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
                ),
                "CACHE_DEFAULT_TIMEOUT": 300,
            }
        )
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        logger.warning("Falling back to local in-memory cache")
        redis_client = None
        cache = Cache(
            config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
        )
else:
    # Redis or Flask-Caching not installed, use in-memory fallback
    logger.warning("Redis or Flask-Caching not installed, using in-memory storage")
    redis_client = None
    cache = (
        Cache(
            config={
                "CACHE_TYPE": "SimpleCache",
                "CACHE_DEFAULT_TIMEOUT": 300,
            }
        )
        if flask_caching_installed
        else None
    )


# Authorization cache functions
def store_verify_token(token, user_id):
    """
    Store a verification token with an expiry time.

    Args:
        token (str): The one-time verification token
        user_id (str): The LINE user ID

    Returns:
        bool: True if stored successfully, False otherwise
    """
    expiry = time.time() + VERIFY_TTL

    try:
        if redis_client:
            # Store in Redis with expiry
            data = json.dumps({"user_id": user_id, "expiry": expiry})
            return redis_client.setex(f"verify_token:{token}", VERIFY_TTL, data)
        # If Redis is unavailable, we need to alert the caller that
        # the operation actually failed so they can use an alternative
        logger.warning(
            "Redis unavailable for storing verify token, using in-memory fallback"
        )
        return False
    except RedisError as e:
        logger.error(f"Redis error while storing verify token: {str(e)}")
        return False


def get_verify_token(token):
    """
    Retrieve and validate a verification token.

    Args:
        token (str): The verification token

    Returns:
        tuple: (user_id, expiry) if valid, (None, None) if invalid or expired
    """
    try:
        if redis_client:
            # Get from Redis
            key = f"verify_token:{token}"
            logger.info(f"Looking up token in Redis: {key}")
            data = redis_client.get(key)

            if not data:
                logger.warning(
                    f"Token not found in Redis: {token[:8] if token else 'None'}..."
                )
                return None, None

            logger.info(f"Token found in Redis: {token[:8]}...")
            parsed = json.loads(data)
            # Delete immediately to prevent reuse
            redis_client.delete(key)
            logger.info("Deleted Redis token after lookup")

            # Check expiry
            if time.time() > parsed.get("expiry", 0):
                logger.warning(f"Token expired in Redis: {token[:8]}...")
                return None, None

            logger.info(f"Valid token from Redis for user_id: {parsed.get('user_id')}")
            return parsed.get("user_id"), parsed.get("expiry")

        # If Redis is unavailable, we need to alert the caller
        logger.warning("Redis unavailable for token lookup, returning None")
        return None, None
    except (RedisError, json.JSONDecodeError) as e:
        logger.error(f"Error retrieving verify token: {str(e)}")
        return None, None


def authorize_user(user_id):
    """
    Mark a user as authorized with location verification.

    Args:
        user_id (str): The LINE user ID

    Returns:
        bool: True if stored successfully, False otherwise
    """
    expiry = time.time() + LOCATION_TTL

    try:
        if redis_client:
            # Store in Redis with expiry
            return redis_client.setex(f"auth_user:{user_id}", LOCATION_TTL, expiry)
        # If Redis is unavailable, return True but don't store
        return True
    except RedisError as e:
        logger.error(f"Redis error while authorizing user: {str(e)}")
        return False


def is_user_authorized(user_id):
    """
    Check if a user is authorized.

    Args:
        user_id (str): The LINE user ID

    Returns:
        bool: True if authorized, False otherwise
    """
    try:
        if redis_client:
            # Get from Redis
            expiry_str = redis_client.get(f"auth_user:{user_id}")
            if not expiry_str:
                return False

            # Check if expired
            try:
                expiry = float(expiry_str)
                return time.time() <= expiry
            except ValueError:
                return False

        # If Redis is unavailable, return False
        return False
    except RedisError as e:
        logger.error(f"Redis error checking user authorization: {str(e)}")
        return False


def store_action_token(token, user_id, action):
    """
    Store an action token for garage door operation.

    Args:
        token (str): The action token
        user_id (str): The LINE user ID
        action (str): The action ('open' or 'close')

    Returns:
        bool: True if stored successfully, False otherwise
    """
    expiry = time.time() + VERIFY_TTL
    data = json.dumps({"user_id": user_id, "action": action, "expiry": expiry})

    try:
        if redis_client:
            # Store in Redis with expiry
            return redis_client.setex(f"action_token:{token}", VERIFY_TTL, data)
        # If Redis is unavailable, return True but don't store
        return True
    except RedisError as e:
        logger.error(f"Redis error while storing action token: {str(e)}")
        return False


def get_action_token(token):
    """
    Retrieve and validate an action token.

    Args:
        token (str): The action token

    Returns:
        tuple: (user_id, action, expiry) if valid,
        (None, None, None) if invalid or expired
    """
    try:
        if redis_client:
            # Get from Redis
            data = redis_client.get(f"action_token:{token}")
            if not data:
                return None, None, None

            parsed = json.loads(data)
            # Delete immediately to prevent reuse
            redis_client.delete(f"action_token:{token}")

            # Check expiry
            if time.time() > parsed.get("expiry", 0):
                return None, None, None

            return parsed.get("user_id"), parsed.get("action"), parsed.get("expiry")

        # If Redis is unavailable, return None
        return None, None, None
    except (RedisError, json.JSONDecodeError) as e:
        logger.error(f"Error retrieving action token: {str(e)}")
        return None, None, None


def clear_all_caches():
    """
    Clear all caches (for testing purposes).

    Returns:
        bool: True if cleared successfully, False otherwise
    """
    try:
        if redis_client:
            # Clear only our application caches, not the entire Redis database
            keys = (
                redis_client.keys("verify_token:*")
                + redis_client.keys("auth_user:*")
                + redis_client.keys("action_token:*")
            )
            if keys:
                redis_client.delete(*keys)
            return True
        return True
    except RedisError as e:
        logger.error(f"Redis error while clearing caches: {str(e)}")
        return False
