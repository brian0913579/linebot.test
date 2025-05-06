# LINE Bot Garage Door Controller

A secure and robust LINE Bot service for controlling a garage door remotely through LINE messaging app. The bot allows authenticated users to open and close a garage door after verifying their location.

## Features

- **User Authentication**: Only registered users can control the garage door
- **Geolocation Verification**: Users must be physically present near the garage to control the door
- **Secure Token System**: One-time use tokens for door operations
- **Cache System**: Redis-based caching with in-memory fallback
- **MQTT Integration**: Communicates with garage door controller via secure MQTT
- **Comprehensive Logging**: Detailed logging with different log levels
- **API Documentation**: Swagger/OpenAPI documentation for all endpoints
- **Rate Limiting**: Protects against abuse and DoS attacks
- **Security Headers**: Implements security best practices
- **Robust Error Handling**: Graceful degradation and fallback mechanisms

## Architecture

The project has been reorganized into a more modular structure:

```
/linebot.test/
├── app.py                  # Main Flask application
├── core/                   # Core application modules
│   ├── line_webhook.py     # LINE webhook handlers
│   ├── mqtt_handler.py     # MQTT communication
│   ├── token_manager.py    # Token generation
│   └── models.py           # Database models
├── config/                 # Configuration files
│   ├── config_module.py    # Configuration settings
│   └── secret_manager.py   # Secret management
├── middleware/             # Middleware components
│   ├── middleware.py       # Flask middleware
│   ├── cache_manager.py    # Redis caching
│   └── rate_limiter.py     # Rate limiting
├── utils/                  # Utility modules
│   ├── logger_config.py    # Logging configuration
│   ├── createUserDatabase.py
│   └── insertUsertoDatabase.py
├── docs/                   # Documentation
│   └── api_docs.py         # API documentation
├── tests/                  # Test suite
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_line_webhook.py
│   ├── test_mqtt_handler.py
│   └── test_token_manager.py
├── static/                 # Static files
│   └── index.html          # Documentation homepage
├── templates/              # HTML templates
│   └── error.html          # Error page template
├── scripts/                # Deployment and maintenance scripts
│   ├── start.sh            # Startup script
│   └── deploy.sh           # Deployment script
└── requirements.txt        # Project dependencies
```

## Prerequisites

- Python 3.9 or higher
- SQLite database
- LINE Developer account and channel
- MQTT broker for garage door communication
- Redis server (optional, falls back to in-memory cache)

## Setup and Installation

### 1. Clone the Repository

```bash
git clone https://github.com/brian13579/linebot.test.git
cd linebot.test
```

### 2. Create and Activate Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # For Linux/Mac
# or
venv\Scripts\activate  # For Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# LINE Bot Configuration
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_token
LINE_CHANNEL_SECRET=your_line_channel_secret

# MQTT Configuration
MQTT_BROKER=your_mqtt_broker_address
MQTT_PORT=8883
MQTT_USERNAME=your_mqtt_username
MQTT_PASSWORD=your_mqtt_password
MQTT_CAFILE=ca.crt
MQTT_TOPIC=garage/command

# Location Configuration
PARK_LAT=24.79155
PARK_LNG=120.99442
MAX_DIST_KM=0.5

# App Configuration
PORT=8080
VERIFY_URL_BASE=https://yourdomain.com/verify-location

# Redis Configuration (optional)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_SSL=false
CACHE_ENABLED=true

# Security Configuration
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=30
```

### 5. Initialize the Database

This creates a SQLite database to store authorized users:

```bash
python utils/createUserDatabase.py
```

### 6. Add Authorized Users

```bash
# Run the script and follow the prompts
python utils/insertUsertoDatabase.py
```

Or directly edit the script to add users:

```python
# Open utils/insertUsertoDatabase.py and add your users
insert_user('LINE_USER_ID_1', 'User Name 1')
insert_user('LINE_USER_ID_2', 'User Name 2')
```

### 7. Start the Application

For development:

```bash
python app.py
```

For production:

```bash
bash scripts/start.sh
```

## Deployment

### Local Deployment

For local deployment, you can use the `start.sh` script:

```bash
bash scripts/start.sh
```

### Server Deployment

The application includes `app.yaml` for Google App Engine deployment and `Procfile` for Heroku deployment.

#### Google App Engine

```bash
gcloud app deploy app.yaml
```

#### Heroku

```bash
git push heroku main
```

## API Documentation

The application includes Swagger/OpenAPI documentation accessible at `/api/docs` when the application is running.

## Testing

Run the test suite with pytest:

```bash
pytest tests/
```

For coverage report:

```bash
pytest --cov=. tests/
```

## Security Features

1. **Request Signature Validation**: All LINE webhook requests are validated
2. **Rate Limiting**: Prevents abuse with IP-based rate limits
3. **Security Headers**: Implements HSTS, XSS protection, etc.
4. **One-time tokens**: All door operation tokens are single-use
5. **Location Verification**: Validates user is physically present
6. **Redis Integration**: Distributed token storage with in-memory fallback
7. **HTTPS Communication**: All communication is encrypted

## Customization

### Changing Location Settings

To change the allowed garage location or distance, update the `.env` file or modify `config/config_module.py`:

```python
# Location Verification Configuration
PARK_LAT = float(get_secret('PARK_LAT', default='24.79155')) 
PARK_LNG = float(get_secret('PARK_LNG', default='120.99442'))
MAX_DIST_KM = float(get_secret('MAX_DIST_KM', default='0.5'))
```

### Modifying User Database

To add/remove users, use the utility scripts:

```bash
python utils/insertUsertoDatabase.py  # Follow prompts to add users
```

## Contributions

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.