import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

SECRETS_BACKEND = os.getenv("SECRETS_BACKEND", "env").lower()
USE_GOOGLE_SECRET_MANAGER = SECRETS_BACKEND == "gcp"

if USE_GOOGLE_SECRET_MANAGER:
    try:
        from google.cloud import secretmanager

        GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not GCP_PROJECT_ID:
            logger.warning(
                "Google Cloud Secret Manager enabled but GOOGLE_CLOUD_PROJECT not set"
            )
    except ImportError:
        logger.error("google-cloud-secret-manager not installed")
        USE_GOOGLE_SECRET_MANAGER = False


@lru_cache(maxsize=32)
def _get_secret_from_gcp(secret_name):
    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_path = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(name=secret_path)
        return response.payload.data.decode("UTF-8")
    except Exception:
        logger.error(f"Error retrieving {secret_name} from GCP.")
        return None


def get_secret(secret_name, default=None):
    env_value = os.getenv(secret_name)
    if env_value:
        return env_value
    if USE_GOOGLE_SECRET_MANAGER:
        gcp_value = _get_secret_from_gcp(secret_name)
        if gcp_value:
            return gcp_value
    return default


class Config:
    """Base Configuration."""

    # Core Toggle
    CACHE_ENABLED = get_secret("CACHE_ENABLED", default="false").lower() in (
        "true",
        "1",
        "yes",
    )

    # LINE Bot Configuration
    LINE_CHANNEL_ACCESS_TOKEN = get_secret("LINE_CHANNEL_ACCESS_TOKEN")
    LINE_CHANNEL_SECRET = get_secret("LINE_CHANNEL_SECRET")

    # MQTT Configuration
    MQTT_BROKER = get_secret(
        "MQTT_BROKER", default="d8e42404.ala.asia-southeast1.emqxsl.com"
    )
    MQTT_PORT = int(get_secret("MQTT_PORT", default="8883"))
    MQTT_USERNAME = get_secret("MQTT_USERNAME", default="piuser")
    MQTT_PASSWORD = get_secret("MQTT_PASSWORD", default="cool.com")
    MQTT_TOPIC = get_secret("MQTT_TOPIC", default="garage/command")

    # Location Verification
    PARK_LAT = float(get_secret("PARK_LAT", default="24.79155"))
    PARK_LNG = float(get_secret("PARK_LNG", default="120.99442"))
    MAX_DIST_KM = float(get_secret("MAX_DIST_KM", default="1.0"))
    MAX_ACCURACY_METERS = float(get_secret("MAX_ACCURACY_METERS", default="250"))
    VERIFY_TTL = int(get_secret("VERIFY_TTL", default="300"))
    LOCATION_TTL = int(get_secret("LOCATION_TTL", default="300"))
    CAMERA_TOKEN_TTL = int(get_secret("CAMERA_TOKEN_TTL", default="3600"))
    YOUTUBE_LIVE_URL = get_secret("YOUTUBE_LIVE_URL", default="")
    VERIFY_URL_BASE = get_secret(
        "VERIFY_URL_BASE", default="https://bri4nting.duckdns.org/verify-location"
    )

    # Redis Configuration
    REDIS_HOST = get_secret("REDIS_HOST", default="localhost")
    REDIS_PORT = int(get_secret("REDIS_PORT", default="6379"))
    REDIS_PASSWORD = get_secret("REDIS_PASSWORD", default=None)
    REDIS_DB = int(get_secret("REDIS_DB", default="0"))
    REDIS_SSL = get_secret("REDIS_SSL", default="false").lower() in ("true", "1", "yes")

    # Security
    import secrets as py_secrets

    SECRET_KEY = get_secret("FLASK_SECRET_KEY", default=py_secrets.token_hex(16))
    ADMIN_USERNAME = get_secret("ADMIN_USERNAME", default="admin")
    ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", default="password")

    RATE_LIMIT_ENABLED = (
        get_secret("RATE_LIMIT_ENABLED", default="false").lower() == "true"
    )
    MAX_REQUESTS_PER_MINUTE = int(get_secret("MAX_REQUESTS_PER_MINUTE", default="30"))

    # Debug Mode
    DEBUG_MODE = get_secret("DEBUG_MODE", default="false").lower() in (
        "true",
        "1",
        "yes",
    )
    debug_users = get_secret("DEBUG_USER_IDS", default="")
    DEBUG_USER_IDS = (
        [user.strip() for user in debug_users.split(",") if user.strip()]
        if debug_users
        else []
    )

    @classmethod
    def validate(cls):
        missing = []
        if not cls.LINE_CHANNEL_ACCESS_TOKEN:
            missing.append("LINE_CHANNEL_ACCESS_TOKEN")
        if not cls.LINE_CHANNEL_SECRET:
            missing.append("LINE_CHANNEL_SECRET")
        if missing:
            raise RuntimeError(f"Missing required secrets: {', '.join(missing)}")
