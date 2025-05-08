import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))

"""
API Documentation Module

This module provides Swagger/OpenAPI documentation for the LineBot API endpoints.
It uses flask-swagger-ui to serve the documentation and apispec to generate the specs.
"""

import importlib.util
from flask import Blueprint, jsonify, current_app
from utils.logger_config import get_logger

# Configure logger
logger = get_logger(__name__)

# Check if necessary modules are available
swagger_ui_installed = importlib.util.find_spec("flask_swagger_ui") is not None
apispec_installed = importlib.util.find_spec("apispec") is not None

# Store endpoint documentation for later processing
endpoint_registry = []

api_docs_blueprint = Blueprint('api_docs', __name__)

if swagger_ui_installed and apispec_installed:
    from flask_swagger_ui import get_swaggerui_blueprint
    from apispec import APISpec
    from apispec.ext.marshmallow import MarshmallowPlugin
    from apispec_webframeworks.flask import FlaskPlugin

    # Import and configure APISpec - the actual spec will be created per request

    # Setup Swagger UI blueprint
    SWAGGER_URL = '/api/docs'  # URL for accessing API docs UI
    API_URL = '/api/spec'      # URL for accessing OpenAPI spec

    swaggerui_blueprint = get_swaggerui_blueprint(
        SWAGGER_URL,
        API_URL,
        config={
            'app_name': "LineBot API Documentation",
            'layout': 'BaseLayout'
        }
    )

    # Register view to serve OpenAPI spec
    @api_docs_blueprint.route('/spec')
    def get_apispec():
        """Generate OpenAPI specification"""
        # Create fresh spec for each request
        current_spec = APISpec(
            title="LineBot API",
            version="1.0.0",
            openapi_version="3.0.2",
            info=dict(
                description="LINE Bot API for garage door control",
                contact=dict(email="admin@example.com")
            ),
            plugins=[FlaskPlugin(), MarshmallowPlugin()],
        )
        
        # Add schemas
        current_spec.components.schema(
            "LocationVerificationRequest", 
            {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "format": "float", "description": "Latitude coordinate"},
                    "lng": {"type": "number", "format": "float", "description": "Longitude coordinate"},
                    "acc": {"type": "number", "format": "float", "description": "Accuracy in meters"}
                },
                "required": ["lat", "lng"]
            }
        )
        
        current_spec.components.schema(
            "LocationVerificationResponse", 
            {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean", "description": "Whether verification was successful"},
                    "message": {"type": "string", "description": "Error message if not successful"}
                },
                "required": ["ok"]
            }
        )
        
        current_spec.components.schema(
            "Error", 
            {
                "type": "object",
                "properties": {
                    "error": {"type": "string", "description": "Error message"}
                },
                "required": ["error"]
            }
        )
        
        # Add paths from registry
        for doc in endpoint_registry:
            try:
                current_spec.path(
                    path=doc['path'],
                    operations=doc['operations']
                )
            except Exception as e:
                logger.warning(f"Failed to document endpoint {doc['path']}: {str(e)}")
                
        return jsonify(current_spec.to_dict())

    def register_swagger_ui(app):
        """Register Swagger UI with Flask app"""
        app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)
        app.register_blueprint(api_docs_blueprint, url_prefix='/api')
        logger.info("Swagger UI registered at %s", SWAGGER_URL)
        return app

    def document_api(view_function, endpoint, methods, location='path', **kwargs):
        """
        Document a Flask API endpoint using apispec.
        
        Args:
            view_function: The Flask view function to document
            endpoint: The endpoint string (without /api prefix)
            methods: HTTP methods as list (e.g., ['GET', 'POST'])
            location: Where parameters are passed ('path', 'query', or 'body')
            **kwargs: Additional documentation parameters
        """
        operations = {}
        
        for method in methods:
            operations[method.lower()] = kwargs
            
        # Store the documentation in the global registry
        endpoint_registry.append({
            'path': f"/api{endpoint}",
            'operations': operations
        })

else:
    # Create dummy functions when Swagger UI or APISpec is not installed
    def register_swagger_ui(app):
        """Dummy function when Swagger UI is not installed"""
        app.register_blueprint(api_docs_blueprint, url_prefix='/api')
        return app

    def document_api(view_function, endpoint, methods, location='path', **kwargs):
        """Dummy function when APISpec is not installed"""
        pass

    @api_docs_blueprint.route('/docs')
    def api_docs_unavailable():
        return jsonify({
            'error': 'API documentation is unavailable. Install flask-swagger-ui and apispec.'
        }), 503