"""
Rate Limiter Module

This module implements rate limiting functionality to protect the API
endpoints from abuse and potential DoS attacks. It uses Flask-Limiter to
enforce request rate limits based on IP address, user ID, or other identifiers.
"""

from flask import jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config.config_module import MAX_REQUESTS_PER_MINUTE, RATE_LIMIT_ENABLED
from utils.logger_config import get_logger

# Configure logger
logger = get_logger(__name__)

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{MAX_REQUESTS_PER_MINUTE} per minute"],
    storage_uri="memory://",
    strategy="fixed-window",
)


def configure_limiter(app):
    """
    Configure the rate limiter for the application.

    Args:
        app: Flask application instance
    """
    if not RATE_LIMIT_ENABLED:
        logger.info("Rate limiting is disabled")
        return

    # Set up limiter with the app
    limiter.init_app(app)

    # Custom rate limit exceeded handler
    @app.errorhandler(429)
    def ratelimit_handler(e):
        logger.warning(f"Rate limit exceeded: {request.remote_addr} - {request.path}")
        return jsonify(error="Rate limit exceeded. Please try again later."), 429

    logger.info(f"Rate limiting enabled: {MAX_REQUESTS_PER_MINUTE} requests per minute")


def limit_webhook_endpoint(app):
    """
    Apply rate limiting to the webhook endpoint.
    This is important to prevent webhook abuse.

    Args:
        app: Flask application instance
    """
    if not RATE_LIMIT_ENABLED:
        return

    # Apply specific limits to the webhook endpoint
    limiter.limit(f"{MAX_REQUESTS_PER_MINUTE} per minute")(
        app.view_functions["webhook"]
    )
    logger.info(
        f"Applied rate limit to webhook endpoint: {MAX_REQUESTS_PER_MINUTE} requests per minute"
    )


def limit_verify_location_endpoint(app):
    """
    Apply rate limiting to the verify-location endpoint.
    This endpoint requires less stringent limits as it's used for location verification.

    Args:
        app: Flask application instance
    """
    if not RATE_LIMIT_ENABLED:
        return

    # Apply specific limits to the verify-location endpoint
    # Use a higher limit for this endpoint as it's used during normal operation
    twice_limit = MAX_REQUESTS_PER_MINUTE * 2
    limiter.limit(f"{twice_limit} per minute")(app.view_functions["verify_location"])
    logger.info(
        f"Applied rate limit to verify-location endpoint: {twice_limit} requests per minute"
    )
