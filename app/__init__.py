import logging

from flask import Flask, jsonify

from app.config import Config
from app.extensions import limiter


def create_app(config_class=Config):
    """
    Application Factory for the Flask app.
    Initializes Flask application with configured dependencies and routes.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Basic logging configuration for the entire application
    logging.basicConfig(
        level=logging.DEBUG if app.config["DEBUG_MODE"] else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Validate mandatory secrets
    config_class.validate()

    # Initialize extensions
    if app.config["RATE_LIMIT_ENABLED"]:
        app.config["RATELIMIT_DEFAULT"] = (
            f"{app.config['MAX_REQUESTS_PER_MINUTE']} per minute"
        )
        limiter.init_app(app)
        logging.info(
            f"Rate limiting enabled: {app.config['MAX_REQUESTS_PER_MINUTE']} req/min"
        )
    else:
        logging.info("Rate limiting is disabled via config")

    # Health check route directly on app
    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "ok", "message": "Service is running"}), 200

    # Avoid rate-limit on healthcheck if enabled
    if app.config["RATE_LIMIT_ENABLED"]:
        limiter.exempt(health_check)

    @app.before_request
    def log_request_info():
        from flask import request

        logging.debug(
            f"Request: {request.method} {request.path} from {request.remote_addr}"
        )

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    # Initialize Services
    from app.services.line_service import line_service
    from app.services.token_service import token_service

    token_service.init_app(app)
    line_service.init_app(app)

    # Register blueprints
    from app.api.admin import admin_bp
    from app.api.location import location_bp
    from app.api.webhooks import webhooks_bp

    app.register_blueprint(webhooks_bp)  # Registers at /webhook
    app.register_blueprint(location_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    return app
