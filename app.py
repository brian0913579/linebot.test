import logging
from logging.config import dictConfig
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException
from rate_limiter import configure_limiter, limit_webhook_endpoint, limit_verify_location_endpoint
import importlib.util

from config_module import PORT, CACHE_ENABLED

# Initialize Flask application
app = Flask(__name__)

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

# Health check endpoint
@app.route("/healthz", methods=["GET"])
def healthz():
    return "OK", 200

# LINE Bot webhook endpoint
@app.route("/webhook", methods=['POST'])
def webhook():
    return webhook_handler()

# Location verification API endpoint
@app.route('/api/verify-location', methods=['POST'])
def verify_location():
    return verify_location_handler()

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