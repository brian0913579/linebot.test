import logging
import os
from logging.config import dictConfig
from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException
from rate_limiter import configure_limiter, limit_webhook_endpoint, limit_verify_location_endpoint
import importlib.util

from config_module import PORT, CACHE_ENABLED

# Initialize Flask application
app = Flask(__name__, static_folder='static')

# Configure rate limiting
configure_limiter(app)

# Check if Flask-Caching is installed
flask_caching_installed = importlib.util.find_spec("flask_caching") is not None

# Initialize Flask-Caching only if available
if CACHE_ENABLED and flask_caching_installed:
    try:
        from cache_manager import cache
        if cache is not None:
            cache.init_app(app)
            app.logger.info("Redis caching enabled")
        else:
            app.logger.warning("Redis caching unavailable, using in-memory storage")
    except ImportError:
        app.logger.warning("Flask-Caching unavailable, using in-memory storage")
else:
    app.logger.info("Caching disabled or Flask-Caching not installed")

# Apply middleware
from middleware import apply_middleware
app = apply_middleware(app)

# Initialize API documentation
from api_docs import register_swagger_ui, document_api
app = register_swagger_ui(app)

# Import webhook handlers after cache setup to avoid circular imports
from line_webhook import webhook_handler, verify_location_handler

# Set up logging
dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'app.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 3,
            'formatter': 'default',
        },
    },
    'loggers': {
        '': {
            'level': 'INFO',
            'handlers': ['console', 'file'],
        },
    }
})

# Root endpoint for documentation
@app.route("/", methods=["GET"])
def index():
    """Serve the API documentation homepage"""
    return send_from_directory(app.static_folder, 'index.html')

# Health check endpoint
@app.route("/healthz", methods=["GET"])
def healthz():
    """
    Health check endpoint.
    ---
    Simple endpoint for monitoring to check if the application is alive.
    """
    return "OK", 200

document_api(
    healthz,
    '/healthz',
    ['GET'],
    description="Health check endpoint",
    summary="Check if the application is alive",
    responses={
        200: {
            "description": "Application is healthy"
        }
    },
    tags=['System']
)

# Import the decorators
from middleware import validate_line_signature, require_json, rate_limit_by_ip

# LINE Bot webhook endpoint
@app.route("/webhook", methods=['POST'])
@validate_line_signature
def webhook():
    """
    LINE Platform webhook endpoint.
    ---
    This endpoint receives webhook events from the LINE Platform.
    """
    return webhook_handler()

document_api(
    webhook,
    '/webhook',
    ['POST'],
    description="LINE Platform webhook endpoint",
    summary="Receive events from LINE Platform",
    responses={
        200: {
            "description": "Webhook processed successfully"
        },
        400: {
            "description": "Invalid signature or request",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Error"}
                }
            }
        }
    },
    tags=['LINE Webhook']
)

# Location verification API endpoint
@app.route('/api/verify-location', methods=['POST'])
@require_json
@rate_limit_by_ip(max_requests=20, time_window=60)  # More strict rate limit for verification
def verify_location():
    """
    Verify user location.
    ---
    This endpoint verifies if a user is within the allowed distance of the garage.
    """
    return verify_location_handler()

document_api(
    verify_location,
    '/verify-location',
    ['POST'],
    description="Verify user location for garage access",
    summary="Verify user location",
    requestBody={
        "description": "Location data to verify",
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/LocationVerificationRequest"}
            }
        }
    },
    responses={
        200: {
            "description": "Location verification result",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/LocationVerificationResponse"}
                }
            }
        },
        400: {
            "description": "Invalid request or parameters",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Error"}
                }
            }
        },
        429: {
            "description": "Too many requests, rate limit exceeded",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Error"}
                }
            }
        }
    },
    tags=['Location API'],
    parameters=[
        {
            "name": "token",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "One-time verification token"
        }
    ]
)

# Error handler for unexpected exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # Log all other exceptions
    app.logger.error(f"Unhandled exception: {e}")
    return "Internal Server Error", 500

# Apply rate limits to specific endpoints
limit_webhook_endpoint(app)
limit_verify_location_endpoint(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)