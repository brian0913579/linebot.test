import os
import logging
import math  # Add this import
import paho.mqtt.client as mqtt
from flask import Flask, jsonify, send_from_directory, request
from werkzeug.exceptions import HTTPException
from middleware.rate_limiter import configure_limiter, limit_webhook_endpoint, limit_verify_location_endpoint
import importlib.util

from config.config_module import PORT, CACHE_ENABLED
from utils import setup_logging, get_logger

# Initialize Flask application
app = Flask(__name__, static_folder='static')

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on the earth (specified in decimal degrees).
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))

    # Radius of Earth in kilometers
    r = 6371
    return c * r

# Configure rate limiting
configure_limiter(app)

# Check if Flask-Caching is installed
flask_caching_installed = importlib.util.find_spec("flask_caching") is not None

# Initialize Flask-Caching only if available
if CACHE_ENABLED and flask_caching_installed:
    try:
        from middleware.cache_manager import cache, redis_client
        if cache is not None:
            cache.init_app(app)
            # More accurate caching status based on actual Redis connection
            if redis_client is not None:
                app.logger.info("Redis caching enabled")
            else:
                app.logger.warning("Redis connection failed, using in-memory cache fallback")
        else:
            app.logger.warning("Cache initialization failed, using in-memory storage")
    except ImportError:
        app.logger.warning("Flask-Caching unavailable, using in-memory storage")
else:
    app.logger.info("Caching disabled or Flask-Caching not installed")

# Apply middleware
from middleware.middleware import apply_middleware
app = apply_middleware(app)

# Initialize API documentation
from docs.api_docs import register_swagger_ui, document_api
app = register_swagger_ui(app)

# Import webhook handlers after cache setup to avoid circular imports
from core.line_webhook import webhook_handler, verify_location_handler

# Set up logging
logger = setup_logging()

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
from middleware.middleware import validate_line_signature, require_json, rate_limit_by_ip

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

# Serve the verification page
@app.route('/verify-location', methods=['GET'])
def verify_location_page():
    """
    Serve the location verification page.
    ---
    This page prompts the user to share their location for verification.
    """
    return send_from_directory(app.static_folder, 'verify.html')

@app.route('/mqtt-test', methods=['GET'])
def mqtt_test():
    """
    Test if the MQTT broker is reachable.
    ---
    This endpoint attempts to connect to the MQTT broker and returns the result.
    """
    client = mqtt.Client()

    # Set the MQTT broker details (replace with your values)
    mqtt_broker = os.environ.get("MQTT_BROKER")
    mqtt_port = int(os.environ.get("MQTT_PORT"))
    mqtt_username = os.environ.get("MQTT_USERNAME")
    mqtt_password = os.environ.get("MQTT_PASSWORD")
    mqtt_cafile = os.environ.get("MQTT_CAFILE", "ca.crt")

    # Set up TLS and credentials if necessary
    client.tls_set(ca_certs=mqtt_cafile)
    client.tls_insecure_set(True)  # Allow self-signed certificates
    client.username_pw_set(mqtt_username, mqtt_password)

    try:
        # Attempt to connect to the MQTT broker
        client.connect(mqtt_broker, mqtt_port, 60)

        # Disconnect after testing
        client.disconnect()

        return jsonify({"status": "success", "message": "MQTT broker is reachable."}), 200
    except Exception as e:
        # Return an error if connection fails
        return jsonify({"status": "failure", "message": f"MQTT connection failed: {str(e)}"}), 500

# Location verification API endpoint
@app.route('/api/verify-location', methods=['POST'])
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
    '/api/verify-location',
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

# Error handlers for different HTTP errors
@app.errorhandler(400)
def bad_request_error(e):
    """Handle 400 Bad Request errors"""
    logger.error(f"400 Bad Request: {e}")
    return jsonify({
        'error': 'Bad Request',
        'message': str(e) or "Invalid request parameters"
    }), 400

@app.errorhandler(401)
def unauthorized_error(e):
    """Handle 401 Unauthorized errors"""
    logger.error(f"401 Unauthorized: {e}")
    return jsonify({
        'error': 'Unauthorized',
        'message': str(e) or "Authentication required"
    }), 401

@app.errorhandler(403)
def forbidden_error(e):
    """Handle 403 Forbidden errors"""
    logger.error(f"403 Forbidden: {e}")
    return jsonify({
        'error': 'Forbidden',
        'message': str(e) or "You don't have permission to access this resource"
    }), 403

@app.errorhandler(404)
def not_found_error(e):
    """Handle 404 Not Found errors"""
    logger.error(f"404 Not Found: {request.path}")
    return jsonify({
        'error': 'Not Found',
        'message': f"The requested URL {request.path} was not found on the server"
    }), 404

@app.errorhandler(429)
def rate_limit_error(e):
    """Handle 429 Too Many Requests errors"""
    logger.error(f"429 Rate Limit Exceeded: {request.remote_addr} - {request.path}")
    return jsonify({
        'error': 'Too Many Requests',
        'message': str(e) or "Rate limit exceeded. Please try again later."
    }), 429

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 Internal Server Error errors"""
    logger.error(f"500 Internal Server Error: {e}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': "An unexpected error occurred. Please try again later."
    }), 500

# Error handler for unexpected exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # Log all other exceptions
    logger.error(f"Unhandled exception: {e}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': "An unexpected error occurred. Please try again later."
    }), 500

# Apply rate limits to specific endpoints
limit_webhook_endpoint(app)
limit_verify_location_endpoint(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)