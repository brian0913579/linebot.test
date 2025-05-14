"""
Secret Manager Module

This module provides secure access to all application secrets.
It centralizes secret handling and supports multiple secrets backends:
1. Environment variables (.env) for local development
2. Google Cloud Secret Manager for production
3. (Potential future backends like AWS Secrets Manager, HashiCorp Vault, etc.)

Usage:
    from config.secret_manager import get_secret
    my_secret = get_secret("SECRET_NAME", default=None)
"""

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Configure logger
logger = logging.getLogger(__name__)

# Load .env file if it exists (for local development)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    logger.info(f"Loaded environment variables from {env_path}")

# Determine which secrets backend to use
SECRETS_BACKEND = os.getenv("SECRETS_BACKEND", "env").lower()
USE_GOOGLE_SECRET_MANAGER = SECRETS_BACKEND == "gcp"

# Only import Google Cloud components if actually being used
if USE_GOOGLE_SECRET_MANAGER:
    try:
        from google.cloud import secretmanager

        GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not GCP_PROJECT_ID:
            logger.warning(
                "Google Cloud Secret Manager enabled but GOOGLE_CLOUD_PROJECT not set"
            )
    except ImportError:
        logger.error(
            (
                "Google Cloud Secret Manager requested but "
                "google-cloud-secret-manager not installed"
            )
        )
        USE_GOOGLE_SECRET_MANAGER = False


@lru_cache(maxsize=32)
def _get_secret_from_gcp(secret_name):
    """
    Get a secret from Google Cloud Secret Manager.
    Results are cached to avoid repeated API calls.
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        secret_path = f"projects/{GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(name=secret_path)
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(f"Error retrieving secret '{secret_name}' from GCP: {str(e)}")
        return None


def get_secret(secret_name, default=None):
    """
    Get a secret from the configured secrets backend.

    Args:
        secret_name: Name of the secret to retrieve
        default: Default value if secret isn't found

    Returns:
        The secret value, or the default if not found
    """
    # First check environment variables (takes precedence)
    env_value = os.getenv(secret_name)
    if env_value:
        return env_value

    # Then try Google Cloud Secret Manager if enabled
    if USE_GOOGLE_SECRET_MANAGER:
        gcp_value = _get_secret_from_gcp(secret_name)
        if gcp_value:
            return gcp_value

    # Return default if nothing found
    logger.debug("A secret was not found, using the default value")
    return default


# Required application secrets with validation
def validate_required_secrets():
    """Validate that all required secrets are available"""
    required_secrets = [
        ("LINE_CHANNEL_ACCESS_TOKEN", "LINE Bot channel access token"),
        ("LINE_CHANNEL_SECRET", "LINE Bot channel secret"),
    ]

    missing = []
    for secret_name, description in required_secrets:
        if not get_secret(secret_name):
            missing.append(f"{secret_name} ({description})")

    if missing:
        error_msg = f"Missing required secrets: {', '.join(missing)}"
        logger.critical(
            "One or more required secrets are missing. Please check the configuration."
        )
        raise RuntimeError(error_msg)

    return True
