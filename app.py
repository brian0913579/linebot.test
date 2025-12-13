"""
LineBot Application

This is the main application module for the LineBot service. It provides a Flask-based
web application that handles LINE webhook events, location verification, and MQTT
communication for garage door control. The application includes rate limiting,
caching support, and comprehensive error handling.

Features:
- LINE Platform webhook integration
- Location-based verification system
- MQTT broker communication
- Rate limiting and caching
- Swagger documentation
- Comprehensive error handling
- Health check endpoints

Environment Variables:
    DB_BUCKET: (Deprecated) Google Cloud Storage bucket for database
    DB_FILENAME: (Deprecated) Database filename (default: users.db)
    CRT_BUCKET: Google Cloud Storage bucket for certificates
    CRT_FILENAME: Certificate filename (default: emqxsl-ca.crt)
    MQTT_BROKER: MQTT broker hostname
    MQTT_PORT: MQTT broker port (default: 1883)
    MQTT_USERNAME: MQTT authentication username
    MQTT_PASSWORD: MQTT authentication password
    MQTT_CAFILE: Path to MQTT CA certificate file
"""

import importlib.util
import math  # Add this import
import os

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request, send_from_directory
from google.cloud import storage
from werkzeug.exceptions import HTTPException

from config.config_module import CACHE_ENABLED, PORT
from core.line_webhook import verify_location_handler, webhook_handler
from docs.api_docs import document_api, register_swagger_ui
from middleware.middleware import apply_middleware, rate_limit_by_ip
from middleware.rate_limiter import (
    configure_limiter,
    limit_verify_location_endpoint,
    limit_webhook_endpoint,
)
from utils.logger_config import setup_logging
from core.models import get_allowed_users, add_user, remove_user
from functools import wraps
from flask import Response, flash, redirect, url_for, session, render_template
from config.secret_manager import get_secret

# Simple Basic Auth
def check_auth(username, password):
    """Check if a username/password combination is valid."""
    # Fetch from Secret Manager (or .env locally)
    expected_username = get_secret("ADMIN_USERNAME", "admin")
    expected_password = get_secret("ADMIN_PASSWORD", "password")
    
    # If using defaults, log a warning (optional but good practice)
    if expected_password == "password":
        logger.warning("Using default admin password! Please set ADMIN_PASSWORD.")
        
    return username == expected_username and password == expected_password

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# Persistence initialization: download DB and CA cert from Cloud Storage into /tmp
def init_persistence():
    """
    Download the user database and CA certificate from Cloud Storage into /tmp
    if configured.
    """
    try:
        client = storage.Client()
        # Database
        # Database download removed (Migrated to Firestore)
        # db_bucket = os.environ.get("DB_BUCKET")
        # db_filename = os.environ.get("DB_FILENAME", "users.db")


        # Certificate
        crt_bucket = os.environ.get("CRT_BUCKET")
        crt_filename = os.environ.get("CRT_FILENAME", "emqxsl-ca.crt")
        if crt_bucket:
            try:
                crt_blob = client.bucket(crt_bucket).blob(crt_filename)
                crt_dest = f"/tmp/{crt_filename}"
                crt_blob.download_to_filename(crt_dest)
                print(f"Downloaded certificate file: {crt_dest}")
            except Exception as e:
                print(f"Warning: Could not download certificate file: {e}")
    except Exception as e:
        print(f"Warning: Could not initialize persistence: {e}")
        # Don't fail app startup if persistence fails


# Initialize Flask application
app = Flask(__name__, static_folder="static")

# Set up logging early
logger = setup_logging()
logger.info("Starting LINE Bot application...")

# Download DB and CA cert from Cloud Storage into /tmp
logger.info("Initializing persistence...")
init_persistence()
logger.info("Persistence initialization completed")


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on the earth
    (specified in decimal degrees).
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
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
                app.logger.warning(
                    "Redis connection failed, using in-memory cache fallback"
                )
        else:
            app.logger.warning("Cache initialization failed, using in-memory storage")
    except ImportError:
        app.logger.warning("Flask-Caching unavailable, using in-memory storage")
else:
    app.logger.info("Caching disabled or Flask-Caching not installed")

app = apply_middleware(app)

app = register_swagger_ui(app)

# Logger is already set up earlier
logger.info("Application setup completed")

# Validate required secrets after app initialization
try:
    from config.secret_manager import validate_required_secrets

    validate_required_secrets()
    logger.info("Secret validation passed")
except Exception as e:
    logger.error(f"Secret validation failed: {e}")
    # Continue anyway for now to allow debugging
    logger.warning("Continuing with startup despite secret validation failure")


# Root endpoint for documentation
@app.route("/", methods=["GET"])
def index():
    """Serve the API documentation homepage"""
    return send_from_directory(app.static_folder or "static", "index.html")


# Health check endpoint
@app.route("/healthz", methods=["GET"])
def healthz():
    """
    Health check endpoint.
    ---
    Simple endpoint for monitoring to check if the application is alive.
    """
    return "OK", 200


# Startup status endpoint for debugging
@app.route("/startup", methods=["GET"])
def startup_status():
    """
    Startup status endpoint for debugging App Engine deployment.
    """
    import sys

    status = {
        "status": "running",
        "python_version": sys.version,
        "port": PORT,
        "db_bucket": os.environ.get("DB_BUCKET", "not set"),
        "crt_bucket": os.environ.get("CRT_BUCKET", "not set"),
        "cache_enabled": CACHE_ENABLED,
    }
    return jsonify(status)


document_api(
    healthz,
    "/healthz",
    ["GET"],
    description="Health check endpoint",
    summary="Check if the application is alive",
    responses={200: {"description": "Application is healthy"}},
    tags=["System"],
)


# Second health check endpoint
@app.route("/health", methods=["GET"])
def health():
    """
    Alternative health check endpoint.
    ---
    Simple endpoint for monitoring to check if the application is alive.
    """
    return "OK", 200


document_api(
    health,
    "/health",
    ["GET"],
    description="Alternative health check endpoint",
    summary="Check if the application is alive",
    responses={200: {"description": "Application is healthy"}},
    tags=["System"],
)


# LINE Bot webhook endpoint
@app.route("/webhook", methods=["POST"])
def webhook():
    """
    LINE Platform webhook endpoint.
    ---
    This endpoint receives webhook events from the LINE Platform.
    """
    return webhook_handler()


document_api(
    webhook,
    "/webhook",
    ["POST"],
    description="LINE Platform webhook endpoint",
    summary="Receive events from LINE Platform",
    responses={
        200: {"description": "Webhook processed successfully"},
        400: {
            "description": "Invalid signature or request",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        },
    },
    tags=["LINE Webhook"],
)


# Serve the verification page
@app.route("/verify-location", methods=["GET"])
def verify_location_page():
    """
    Serve the location verification page.
    ---
    This page prompts the user to share their location for verification.
    """
    return send_from_directory(app.static_folder or "static", "verify.html")


@app.route("/mqtt-test", methods=["GET"])
def mqtt_test():
    """
    Test if the MQTT broker is reachable.
    ---
    This endpoint attempts to connect to the MQTT broker and returns the result.
    """
    client = mqtt.Client()

    # Set the MQTT broker details (replace with your values)
    mqtt_broker = os.environ.get("MQTT_BROKER")
    if not mqtt_broker:
        return (
            jsonify({"status": "failure", "message": "MQTT broker not configured."}),
            500,
        )

    mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))
    if not mqtt_port:
        return (
            jsonify({"status": "failure", "message": "MQTT port not configured."}),
            500,
        )

    mqtt_username = os.environ.get("MQTT_USERNAME")
    mqtt_password = os.environ.get("MQTT_PASSWORD")
    cafile = os.environ.get("MQTT_CAFILE")

    # Set up TLS and credentials if necessary
    client.tls_set(ca_certs=cafile)
    # client.tls_insecure_set(True)  # Allow self-signed certificates
    client.username_pw_set(mqtt_username, mqtt_password)

    try:
        # Attempt to connect to the MQTT broker
        client.connect(mqtt_broker, mqtt_port, 60)

        # Disconnect after testing
        client.disconnect()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "MQTT broker is reachable.",
                }
            ),
            200,
        )
    except Exception as e:
        # Log the exception details on the server
        app.logger.error("MQTT connection failed", exc_info=e)
        # Return a generic error message to the user
        return (
            jsonify(
                {
                    "status": "failure",
                    "message": "MQTT connection failed due to an internal error.",
                }
            ),
            500,
        )


# Location verification API endpoint
@app.route("/api/verify-location", methods=["POST"])
@rate_limit_by_ip(
    max_requests=20, time_window=60
)  # More strict rate limit for verification
def verify_location():
    """
    Verify user location.
    ---
    This endpoint verifies if a user is within the allowed distance of the garage.
    """
    return verify_location_handler()


document_api(
    verify_location,
    "/api/verify-location",
    ["POST"],
    description="Verify user location for garage access",
    summary="Verify user location",
    requestBody={
        "description": "Location data to verify",
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/LocationVerificationRequest"}
            }
        },
    },
    responses={
        200: {
            "description": "Location verification result",
            "content": {
                "application/json": {
                    "schema": {
                        "$ref": "#/components/schemas/LocationVerificationResponse"
                    }
                }
            },
        },
        400: {
            "description": "Invalid request or parameters",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        },
        429: {
            "description": "Too many requests, rate limit exceeded",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
            },
        },
    },
    tags=["Location API"],
    parameters=[
        {
            "name": "token",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "One-time verification token",
        }
    ],
)


# Admin Routes
@app.route("/admin", methods=["GET"])
@requires_auth
def admin_dashboard():
    users = get_allowed_users()
    return render_template("admin.html", users=users)

@app.route("/admin/add", methods=["POST"])
@requires_auth
def admin_add():
    user_name = request.form.get("user_name")
    user_id = request.form.get("user_id")
    
    if not user_name or not user_id:
        flash("Please enter complete data", "error")
    else:
        if add_user(user_id, user_name):
            flash(f"Added: {user_name}", "success")
        else:
            flash("Failed to add user", "error")
            
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete", methods=["POST"])
@requires_auth
def admin_delete():
    user_id = request.form.get("user_id")
    if user_id:
        if remove_user(user_id):
            flash(f"Deleted: {user_id}", "success")
        else:
            flash("Failed to delete user", "error")
            
    return redirect(url_for("admin_dashboard"))


# Error handlers for different HTTP errors
@app.errorhandler(400)
def bad_request_error(e):
    """Handle 400 Bad Request errors"""
    logger.error(f"400 Bad Request: {e}")
    return (
        jsonify(
            {"error": "Bad Request", "message": str(e) or "Invalid request parameters"}
        ),
        400,
    )


@app.errorhandler(401)
def unauthorized_error(e):
    """Handle 401 Unauthorized errors"""
    logger.error(f"401 Unauthorized: {e}")
    return (
        jsonify(
            {"error": "Unauthorized", "message": str(e) or "Authentication required"}
        ),
        401,
    )


@app.errorhandler(403)
def forbidden_error(e):
    """Handle 403 Forbidden errors"""
    logger.error(f"403 Forbidden: {e}")
    return (
        jsonify(
            {
                "error": "Forbidden",
                "message": str(e)
                or "You don't have permission to access this resource",
            }
        ),
        403,
    )


@app.errorhandler(404)
def not_found_error(e):
    """Handle 404 Not Found errors"""
    logger.error(f"404 Not Found: {request.path}")
    return (
        jsonify(
            {
                "error": "Not Found",
                "message": (
                    f"The requested URL {request.path} " "was not found on the server"
                ),
            }
        ),
        404,
    )


@app.errorhandler(429)
def rate_limit_error(e):
    """Handle 429 Too Many Requests errors"""
    logger.error(f"429 Rate Limit Exceeded: {request.remote_addr} - {request.path}")
    return (
        jsonify(
            {
                "error": "Too Many Requests",
                "message": str(e) or "Rate limit exceeded. Please try again later.",
            }
        ),
        429,
    )


@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 Internal Server Error errors"""
    logger.error(f"500 Internal Server Error: {e}")
    return (
        jsonify(
            {
                "error": "Internal Server Error",
                "message": "An unexpected error occurred. Please try again later.",
            }
        ),
        500,
    )


# Error handler for unexpected exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # Log all other exceptions
    logger.error(f"Unhandled exception: {e}")
    return (
        jsonify(
            {
                "error": "Internal Server Error",
                "message": "An unexpected error occurred. Please try again later.",
            }
        ),
        500,
    )


# Apply rate limits to specific endpoints
limit_webhook_endpoint(app)
limit_verify_location_endpoint(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
