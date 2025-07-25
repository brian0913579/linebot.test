"""
Configuration Module

This module centralizes all application configuration settings
and loads values from appropriate sources.
"""

from config.secret_manager import get_secret

# NOTE: Secret validation is now done in app.py after initialization
# validate_required_secrets() - moved to app startup

# Caching toggle
CACHE_ENABLED = get_secret("CACHE_ENABLED", default="false").lower() in (
    "true",
    "1",
    "yes",
)

# Line Bot Configuration
LINE_CHANNEL_ACCESS_TOKEN = get_secret("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = get_secret("LINE_CHANNEL_SECRET")

# MQTT Broker Configuration
MQTT_BROKER = get_secret(
    "MQTT_BROKER", default="d8e42404.ala.asia-southeast1.emqxsl.com"
)
MQTT_PORT = int(get_secret("MQTT_PORT", default="8883"))
MQTT_USERNAME = get_secret("MQTT_USERNAME", default="piuser")
MQTT_PASSWORD = get_secret("MQTT_PASSWORD", default="cool.com")
MQTT_TOPIC = get_secret("MQTT_TOPIC", default="garage/command")

# Location Verification Configuration
PARK_LAT = float(get_secret("PARK_LAT", default="24.79155"))  # Parking lot latitude
PARK_LNG = float(get_secret("PARK_LNG", default="120.99442"))  # Parking lot longitude
MAX_DIST_KM = float(
    get_secret("MAX_DIST_KM", default="0.5")
)  # 500 meters maximum distance

# Time-to-live settings
VERIFY_TTL = int(
    get_secret("VERIFY_TTL", default="300")
)  # 5 minutes for one-time verification tokens
LOCATION_TTL = int(
    get_secret("LOCATION_TTL", default="300")
)  # 5 minutes location verification validity

# Redis Configuration
REDIS_HOST = get_secret("REDIS_HOST", default="localhost")
REDIS_PORT = int(get_secret("REDIS_PORT", default="6379"))
REDIS_PASSWORD = get_secret("REDIS_PASSWORD", default=None)
REDIS_DB = int(get_secret("REDIS_DB", default="0"))
REDIS_SSL = get_secret("REDIS_SSL", default="false").lower() in ("true", "1", "yes")

# Flask App Configuration
PORT = int(get_secret("PORT", default="8080"))
VERIFY_URL_BASE = get_secret(
    "VERIFY_URL_BASE", default="https://bri4nting.duckdns.org/verify-location"
)

# Security Configuration
RATE_LIMIT_ENABLED = get_secret("RATE_LIMIT_ENABLED", default="false").lower() == "true"
MAX_REQUESTS_PER_MINUTE = int(get_secret("MAX_REQUESTS_PER_MINUTE", default="30"))
