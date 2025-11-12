
# LINE Bot Garage Door Controller
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/10563/badge)](https://www.bestpractices.dev/projects/10563)

A secure, robust LINE Bot service for remotely controlling a garage door via the LINE messaging platform. Authenticated users can open and close the garage door only after verifying they are physically present at the configured location.

<img src="static/demo.gif" width="400px" alt="LINE Bot Demo" />

## Table of Contents

- [Features](#features)
- [System Architecture](#system-architecture)
- [Security Features](#security-features)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Local Development](#local-development)
  - [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [User Management](#user-management)
- [MQTT Integration](#mqtt-integration)
- [API Documentation](#api-documentation)
- [Logging](#logging)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)
- [Changelog](#changelog)

## Features

- **User Authentication**: Registered users in MongoDB Atlas (with SQLite fallback) can control the garage door.
- **Database Flexibility**: Primary MongoDB Atlas storage with automatic SQLite fallback for high availability.
- **Geolocation Verification**: Users must be physically present near the garage (configurable radius) to operate the door.
- **One-Time Token System**: Secure, single-use tokens prevent replay attacks.
- **TLS-Encrypted MQTT Communication**: Securely communicates with the garage door controller over MQTT.
- **Certificate Validation**: Verifies broker certificates against a trusted CA.
- **Redis Cache (Optional)**: Distributed token storage with in-memory fallback.
- **HMAC Signature Validation**: Verifies all LINE webhook requests.
- **Rate Limiting**: IP-based rate limits protect against abuse.
- **Security Headers**: Implements HSTS, XSS protection, Content-Security-Policy, and other headers.
- **Detailed Logging**: Console logging with configurable levels; file-based logging to `/tmp`.
- **Swagger/OpenAPI Docs**: Interactive API documentation served under `/api/docs`.
- **Static Verification Page**: Browser-based geolocation capture at `/static/verify.html`.

## System Architecture

1. **LINE Webhook Handler** (`/webhook`): Receives messages via LINE Messaging API.
2. **Location Verification** (`/verify-location`): Browser geolocation API posts coordinates for proximity check.
3. **Token Manager**: Generates, stores, and validates single-use tokens.
4. **MQTT Client**: Publishes open/close commands to the garage controller.
5. **Redis Cache**: Optional backend for token and rate-limit state.
6. **Static Pages**: Served from the `static/` directory (verification page).

## Security Features

- HMAC-SHA256 signature validation of incoming LINE requests.
- Single-use tokens with configurable TTL.
- Geofence enforcement using the haversine formula.
- TLS encryption for all HTTP and MQTT traffic.
- Certificate Authority verification of MQTT broker.
- IP-based rate limiting with configurable thresholds.
- Security-focused HTTP headers on all responses.

## Project Structure

```
/linebot.test/
├── app.py                  # Main Flask application
├── app.yaml                # App Engine configuration
├── requirements.txt        # Python dependencies
├── static/                 # Static files (verify.html)
├── core/
│   ├── line_webhook.py     # LINE webhook logic
│   ├── token_manager.py    # Token generation & validation
│   └── mqtt_handler.py     # MQTT publish logic
├── middleware/
│   ├── rate_limiter.py     # Request rate limiting
│   └── security.py         # Signature & header middleware
├── utils/
│   ├── logger_config.py    # Logging setup
│   └── createUserDatabase.py / insertUsertoDatabase.py
├── docs/
│   └── api_docs.py         # Swagger/OpenAPI generator
└── tests/                  # pytest test suite
    ├── test_app.py
    ├── test_line_webhook.py
    ├── test_mqtt_handler.py
    └── test_token_manager.py
```

## Prerequisites

- Python 3.9+
- Google Cloud SDK (for App Engine deployment)
- A LINE Developer account and Messaging API channel
- An MQTT broker (EMQX Cloud, HiveMQ, etc.)
- MongoDB Atlas account (recommended) or SQLite for user storage
- Redis server (optional; falls back to in-memory)
- CA certificate for MQTT broker (if not publicly trusted)
- OS packages: `mosquitto-clients` (for local MQTT testing)
- Copy `.env.example` to `.env` and fill in your credentials

## Installation

## Quick Start

1. Clone the repo and install dependencies.
2. Copy and configure `.env` from `.env.example`.
3. Run `python app.py` (or deploy to App Engine).

### Local Development

```bash
git clone https://github.com/brian13579/linebot.test.git
cd linebot.test
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your credentials and settings
python app.py
```

Visit `http://localhost:8080/static/verify.html?token=TEST` and test `/webhook` via `curl`.

### Production Deployment

#### Google App Engine

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud app create --region=YOUR_REGION
gcloud app deploy app.yaml
```

Update your LINE webhook to `https://YOUR_PROJECT_ID.appspot.com/webhook`.

## Configuration

Create a `.env.example` with:
```env
LINE_CHANNEL_ACCESS_TOKEN=your_access_token
LINE_CHANNEL_SECRET=your_channel_secret
MQTT_BROKER=mqtt.example.com
MQTT_PORT=8883
MQTT_USERNAME=your_user
MQTT_PASSWORD=your_pass
MQTT_TOPIC=garage/command
```

Environment variables (set in `.env` or `app.yaml`):

```env
# LINE Bot credentials
LINE_CHANNEL_ACCESS_TOKEN=
LINE_CHANNEL_SECRET=

# MQTT Broker settings
MQTT_BROKER=
MQTT_PORT=8883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_TOPIC=garage/command
MQTT_CAFILE=ca.crt

# Location verification
PARK_LAT=24.79155
PARK_LNG=120.99442
MAX_DIST_KM=0.5
VERIFY_URL_BASE=https://YOUR_DOMAIN/static/verify.html

# Database settings
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
DB_MODE=mongo  # Options: mongo, sqlite, auto
DB_PATH=/tmp/users.db  # Only used for SQLite

# Redis cache (optional)
REDIS_URL=redis://:password@host:6379/0
CACHE_ENABLED=false

# Rate limiting
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=30
```

## User Management

### MongoDB Atlas Setup (Recommended)

1. **Create MongoDB Atlas Cluster**:
   - Sign up at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
   - Create a free cluster (M0 tier is sufficient)
   - Whitelist your IP addresses or use 0.0.0.0/0 for testing
   - Create a database user with read/write permissions

2. **Get Connection String**:
   - Click "Connect" on your cluster
   - Choose "Connect your application"
   - Copy the connection string (looks like: `mongodb+srv://username:password@cluster.mongodb.net/`)

3. **Configure Environment**:
   ```bash
   export MONGO_URI="mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority"
   export DB_MODE="mongo"
   ```

4. **Add Users**:
   ```bash
   # Add a new authorized user
   python add_user.py add Uea6813ef8ec77e7446090621ebcf472a "John Doe"
   
   # Remove a user
   python add_user.py remove Uea6813ef8ec77e7446090621ebcf472a
   
   # List all authorized users
   python add_user.py list
   ```

### SQLite Fallback

If MongoDB is unavailable or `MONGO_URI` is not set, the system automatically falls back to SQLite:

- Initialize SQLite DB: `python utils/createUserDatabase.py`
- Add users: Edit and run `python utils/insertUsertoDatabase.py`

The fallback is automatic and requires no configuration. The app will log which database mode is active.

### Database Modes

- **mongo**: Use MongoDB Atlas exclusively (fails if unavailable)
- **sqlite**: Use SQLite exclusively (ignores MongoDB)
- **auto** (default): Try MongoDB first, fall back to SQLite if unavailable

## MQTT Integration

Your bot publishes messages to the configured MQTT topic:

```python
client.publish(os.environ['MQTT_TOPIC'], payload='open')
```

Ensure your controller subscribes to the same topic.

## API Documentation

Available at `/api/docs` when the app is running; serves interactive Swagger UI.

## Logging

- **Console**: All logs printed to stdout (captured by Stackdriver).
- **File**: Logs at level INFO+ written to `/tmp/app.log`.
- **Error**: ERROR+ logs to `/tmp/error.log`.

## Testing

Run tests with coverage:

```bash
pytest --cov=. tests/
```

## Troubleshooting

- **SSL Hostname Mismatch**: Regenerate your MQTT broker cert with the correct SAN.
- **502 Bad Gateway on App Engine**: Ensure `/healthz` exists and `script: auto` is configured in `app.yaml`.
- **Permission Denied on Cloud Build**: Grant `roles/cloudbuild.builds.editor` to the Cloud Build service account.

## Contributing

1. Fork the repo
2. Create a feature branch
3. Commit changes
4. Submit a Pull Request

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contact

For questions or issues, please open an issue on the GitHub repo or reach out via email: cool.brian1206cool@gmail.com
