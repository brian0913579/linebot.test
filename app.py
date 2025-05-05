import logging
from logging.config import dictConfig
from flask import Flask
from werkzeug.exceptions import HTTPException

from config_module import PORT
from line_webhook import webhook_handler, verify_location_handler

# Initialize Flask application
app = Flask(__name__)

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)