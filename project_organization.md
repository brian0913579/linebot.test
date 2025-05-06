# Project Organization

## Current Project Structure
```
/linebot.test/
├── app.py                  # Main Flask application
├── line_webhook.py         # LINE webhook handlers
├── mqtt_handler.py         # MQTT communication with garage door
├── token_manager.py        # Token generation and management
├── models.py               # Database models and queries
├── config_module.py        # Configuration settings
├── secret_manager.py       # Secret management
├── middleware.py           # Flask middleware and decorators
├── api_docs.py             # API documentation
├── cache_manager.py        # Redis caching
├── rate_limiter.py         # Rate limiting functionality
├── logger_config.py        # Centralized logging
├── utils/                  # Utility scripts
│   ├── createUserDatabase.py
│   └── insertUsertoDatabase.py
├── tests/                  # Test suite
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_line_webhook.py
│   ├── test_mqtt_handler.py
│   └── test_token_manager.py
├── static/                 # Static files
│   └── index.html
├── requirements.txt        # Project dependencies
├── start.sh                # Startup script for production
├── deploy.sh               # Deployment script
├── Procfile                # Heroku deployment
└── app.yaml                # Google App Engine deployment
```

## Recommended Organization
```
/linebot.test/
├── app.py                  # Main Flask application
├── core/                   # Core application modules
│   ├── __init__.py
│   ├── line_webhook.py     # LINE webhook handlers
│   ├── mqtt_handler.py     # MQTT communication
│   ├── token_manager.py    # Token generation
│   └── models.py           # Database models
├── config/                 # Configuration files
│   ├── __init__.py
│   ├── config_module.py    # Configuration settings
│   └── secret_manager.py   # Secret management
├── middleware/             # Middleware components
│   ├── __init__.py
│   ├── middleware.py       # Flask middleware
│   ├── cache_manager.py    # Redis caching
│   └── rate_limiter.py     # Rate limiting
├── utils/                  # Utility modules
│   ├── __init__.py
│   ├── logger_config.py    # Logging configuration
│   ├── createUserDatabase.py
│   └── insertUsertoDatabase.py
├── docs/                   # Documentation
│   ├── __init__.py
│   └── api_docs.py         # API documentation
├── tests/                  # Test suite
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_line_webhook.py
│   ├── test_mqtt_handler.py
│   └── test_token_manager.py
├── static/                 # Static files
│   └── index.html
├── scripts/                # Deployment and maintenance scripts
│   ├── start.sh            # Startup script
│   └── deploy.sh           # Deployment script
├── requirements.txt        # Project dependencies
├── Procfile                # Heroku deployment
├── app.yaml                # Google App Engine deployment
└── README.md               # Project documentation
```

## Implementation Steps

1. Create necessary directories:
   ```bash
   mkdir -p core config middleware utils docs scripts
   ```

2. Create __init__.py files in each directory
   ```bash
   touch core/__init__.py config/__init__.py middleware/__init__.py utils/__init__.py docs/__init__.py tests/__init__.py
   ```

3. Move files to their new locations
   ```bash
   # Core modules
   mv line_webhook.py mqtt_handler.py token_manager.py models.py core/
   
   # Config modules
   mv config_module.py secret_manager.py config/
   
   # Middleware components
   mv middleware.py cache_manager.py rate_limiter.py middleware/
   
   # Utility modules
   mv logger_config.py utils/
   
   # Documentation
   mv api_docs.py docs/
   
   # Scripts
   mv start.sh deploy.sh scripts/
   ```

4. Update imports in all files to reflect the new structure

5. Test the application to verify everything works with the new structure