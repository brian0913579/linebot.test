"""
Logger Configuration Module

This module provides centralized logging configuration for the application.
It defines log formatters, handlers, and configures the Python logging system.
"""

import logging
from logging.config import dictConfig
import os
from pathlib import Path

# Default log directory
LOG_DIR = Path(os.environ.get('LOG_DIR', '.'))

# Ensure log directory exists
LOG_DIR.mkdir(exist_ok=True)

# Log file path
LOG_FILE = LOG_DIR / 'app.log'

# Log levels
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# Default log configuration
DEFAULT_LOG_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
        },
        'detailed': {
            'format': '%(asctime)s %(name)s [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_FILE),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 3,
            'formatter': 'default',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'error.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 3,
            'formatter': 'detailed',
        },
    },
    'loggers': {
        '': {  # Root logger
            'level': 'INFO',
            'handlers': ['console', 'file', 'error_file'],
        },
        'line_webhook': {  # Specific logger for webhook module
            'level': 'INFO',
            'handlers': ['console', 'file', 'error_file'],
            'propagate': False,
        },
        'mqtt_handler': {  # Specific logger for MQTT module
            'level': 'INFO',
            'handlers': ['console', 'file', 'error_file'],
            'propagate': False,
        },
    }
}

def setup_logging(log_level=None, config=None):
    """
    Set up logging configuration.
    
    Args:
        log_level (str, optional): Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
                                   Defaults to None (uses INFO).
        config (dict, optional): Custom logging configuration dictionary.
                                 Defaults to None (uses DEFAULT_LOG_CONFIG).
    """
    # Start with the default config
    log_config = DEFAULT_LOG_CONFIG.copy()
    
    # Override with custom config if provided
    if config:
        log_config.update(config)
        
    # Override log level if provided
    if log_level:
        level = LOG_LEVELS.get(log_level.upper(), logging.INFO)
        log_config['loggers']['']['level'] = level
        log_config['handlers']['console']['level'] = level
        
    # Apply configuration
    dictConfig(log_config)
    
    # Create a logger to report successful configuration
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level: {log_level or 'INFO'}")
    
    return logger

def get_logger(name):
    """
    Get a logger for a specific module.
    
    Args:
        name (str): Logger name, typically __name__ of the calling module.
        
    Returns:
        Logger: Configured logger instance.
    """
    return logging.getLogger(name)

# Configure logging with default settings if this module is imported directly
if __name__ != '__main__':
    setup_logging(os.environ.get('LOG_LEVEL', 'INFO'))