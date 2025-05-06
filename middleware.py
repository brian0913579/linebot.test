"""
Middleware Module

This module provides middleware functions for Flask application,
including signature validation for LINE webhook requests.
"""

import hashlib
import hmac
import base64
import functools
import time
from flask import request, abort, current_app

from config_module import LINE_CHANNEL_SECRET
from logger_config import get_logger

# Configure logger
logger = get_logger(__name__)

def validate_line_signature(f):
    """
    Decorator middleware to validate LINE webhook signatures.
    
    This middleware validates that incoming webhook requests 
    are actually from LINE by checking the signature in the header.
    
    Args:
        f: The Flask view function to wrap
        
    Returns:
        The wrapped function that validates signatures before processing
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Only validate POST requests to webhook endpoint
        if request.method != 'POST' or not request.path.endswith('/webhook'):
            return f(*args, **kwargs)
            
        signature = request.headers.get('X-Line-Signature')
        if not signature:
            logger.error("Missing X-Line-Signature header")
            abort(400, description="Missing signature header")
            
        body = request.get_data(as_text=True)
        
        # Log request info in debug mode
        logger.debug(f"Webhook request path: {request.path}")
        logger.debug(f"Received signature: {signature}")
        logger.debug(f"Request body length: {len(body)} bytes")
        
        # Validate signature
        try:
            # Calculate expected signature
            expected_signature = base64.b64encode(
                hmac.new(
                    key=LINE_CHANNEL_SECRET.encode(),
                    msg=body.encode(),
                    digestmod=hashlib.sha256
                ).digest()
            ).decode()
            
            if signature != expected_signature:
                logger.error("Invalid LINE webhook signature")
                logger.debug(f"Expected: {expected_signature}")
                logger.debug(f"Received: {signature}")
                abort(400, description="Invalid signature")
                
            logger.debug("LINE webhook signature validated successfully")
            return f(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Error validating signature: {str(e)}")
            abort(400, description="Signature validation error")
            
    return decorated_function

def require_json(f):
    """
    Decorator middleware to ensure requests have valid JSON content.
    
    Args:
        f: The Flask view function to wrap
        
    Returns:
        The wrapped function that validates JSON content
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Only validate POST requests
        if request.method != 'POST':
            return f(*args, **kwargs)
            
        # Check for JSON content type
        content_type = request.headers.get('Content-Type', '')
        if not content_type.startswith('application/json'):
            logger.warning(f"Invalid Content-Type: {content_type}")
            abort(415, description="Content-Type must be application/json")
            
        # Ensure the request has a body
        if not request.data:
            logger.warning("Empty request body")
            abort(400, description="Request body cannot be empty")
            
        # Try to parse JSON
        try:
            request.get_json()
        except Exception as e:
            logger.warning(f"Invalid JSON format: {str(e)}")
            abort(400, description="Invalid JSON format")
            
        return f(*args, **kwargs)
        
    return decorated_function

def rate_limit_by_ip(max_requests=30, time_window=60):
    """
    Decorator middleware to implement IP-based rate limiting.
    
    Args:
        max_requests: Maximum number of requests allowed per time window
        time_window: Time window in seconds
        
    Returns:
        Decorator function
    """
    # Store request counts with timestamps for cleanup
    ip_request_counts = {}
    
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr
            
            # Clean up old entries
            current_time = time.time()
            for tracked_ip in list(ip_request_counts.keys()):
                timestamps = ip_request_counts[tracked_ip]
                # Remove timestamps older than the time window
                while timestamps and timestamps[0] < current_time - time_window:
                    timestamps.pop(0)
                # Remove entry if no timestamps left
                if not timestamps:
                    del ip_request_counts[tracked_ip]
            
            # Check rate limit
            if ip in ip_request_counts:
                if len(ip_request_counts[ip]) >= max_requests:
                    logger.warning(f"Rate limit exceeded for IP: {ip}")
                    abort(429, description="Too many requests")
                ip_request_counts[ip].append(current_time)
            else:
                ip_request_counts[ip] = [current_time]
                
            return f(*args, **kwargs)
            
        return decorated_function
        
    return decorator

def apply_middleware(app):
    """
    Apply all middleware to the Flask application.
    
    Args:
        app: The Flask application instance
    """
    # Register before_request handlers
    @app.before_request
    def log_request_info():
        """Log basic request information for all requests."""
        logger.debug(f"Request: {request.method} {request.path} from {request.remote_addr}")
        
    # Apply security headers
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses."""
        # Prevent content type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Apply XSS protection
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'DENY'
        # Limit referrer information
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # HSTS (only in production)
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
        
    logger.info("Middleware applied successfully")
    return app