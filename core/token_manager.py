"""
token_manager.py

Provides functions for generating, storing,
and cleaning user action tokens with expirations.
"""

import secrets as py_secrets
import time

from config.config_module import VERIFY_TTL

# token_manager.py

TOKENS = {}


def generate_token(user_id):
    """
    Generates two URL-safe tokens ("open" and "close") for the given user_id,
    each valid for 300 seconds from creation.
    Returns a tuple (token_open, token_close).
    """

    token_open = py_secrets.token_urlsafe(16)
    token_close = py_secrets.token_urlsafe(16)

    # Store user_id, action, and expiry for both tokens
    TOKENS[token_open] = (user_id, "open", time.time() + 300)
    TOKENS[token_close] = (user_id, "close", time.time() + 300)

    return token_open, token_close


def store_action_token(token: str, user_id: str, action: str) -> None:
    """
    Store an action token in memory with an expiry timestamp.
    """
    expiry = time.time() + VERIFY_TTL
    TOKENS[token] = (user_id, action, expiry)


def clean_expired_tokens():
    """
    Removes all tokens from the TOKENS dictionary whose expiry timestamp
    is less than or equal to the current time.
    """

    current_time = time.time()
    expired_tokens = list(TOKENS.keys())
    for token in expired_tokens:
        _, _, expiry = TOKENS[token]
        if expiry <= current_time:
            del TOKENS[token]


def invalidate_user_tokens(user_id: str) -> None:
    """
    Immediately invalidates all pending open/close action tokens for a given user.
    Called when a user successfully consumes any token to prevent double-clicking.
    """
    tokens_to_remove = []
    for token, (t_user_id, t_action, t_expiry) in TOKENS.items():
        if t_user_id == user_id and t_action in ("open", "close"):
            tokens_to_remove.append(token)

    for token in tokens_to_remove:
        del TOKENS[token]
