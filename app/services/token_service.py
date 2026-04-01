import json
import secrets as py_secrets
import time

from flask import current_app

from app.models.datastore_client import get_datastore_client

from utils.logger_config import get_logger

logger = get_logger(__name__)


class TokenService:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize TokenService (Datastore initialized lazily via get_datastore_client)."""
        pass

    def _db(self):
        return get_datastore_client()

    # ------------------------------------------------------------------
    # Verify tokens  (one-time use, consumed on first read)
    # ------------------------------------------------------------------

    def store_verify_token(self, token: str, user_id: str, action: str) -> bool:
        expiry = time.time() + current_app.config["VERIFY_TTL"]
        try:
            db = self._db()
            key = db.key("VerifyToken", token)
            # Create a dict first, then build the Datastore Entity
            entity_data = {"user_id": user_id, "action": action, "expiry": expiry}
            from google.cloud import datastore
            entity = datastore.Entity(key=key)
            entity.update(entity_data)
            db.put(entity)
            return True
        except Exception as e:
            logger.error(f"Error storing verify token: {e}")
            return False

    def get_verify_token(self, token: str):
        """Returns (user_id, expiry, action) or (None, None, None) if invalid."""
        try:
            db = self._db()
            key = db.key("VerifyToken", token)
            entity = db.get(key)
            if not entity:
                return None, None, None
            db.delete(key)
            if time.time() > entity.get("expiry", 0):
                return None, None, None
            return entity.get("user_id"), entity.get("expiry"), entity.get("action")
        except Exception as e:
            logger.error(f"Error retrieving verify token: {e}")
            return None, None, None

    # ------------------------------------------------------------------
    # Location authorisation
    # ------------------------------------------------------------------

    def authorize_user(self, user_id: str) -> bool:
        expiry = time.time() + current_app.config["LOCATION_TTL"]
        try:
            db = self._db()
            key = db.key("AuthUser", user_id)
            from google.cloud import datastore
            entity = datastore.Entity(key=key)
            entity.update({"expiry": expiry})
            db.put(entity)
            return True
        except Exception as e:
            logger.error(f"Error authorising user: {e}")
            return False

    def is_user_authorized(self, user_id: str) -> bool:
        try:
            db = self._db()
            key = db.key("AuthUser", user_id)
            entity = db.get(key)
            if entity:
                return time.time() <= float(entity.get("expiry", 0))
            return False
        except Exception as e:
            logger.error(f"Error checking user authorisation: {e}")
            return False

    # Action tokens removed — action is now embedded in the VerifyToken itself.

    # ------------------------------------------------------------------
    # Camera tokens
    # ------------------------------------------------------------------

    def store_camera_token(self, token: str, user_id: str) -> bool:
        expiry = time.time() + current_app.config["CAMERA_TOKEN_TTL"]
        try:
            db = self._db()
            key = db.key("CameraToken", token)
            from google.cloud import datastore
            entity = datastore.Entity(key=key)
            entity.update({"user_id": user_id, "expiry": expiry})
            db.put(entity)
            return True
        except Exception as e:
            logger.error(f"Error storing camera token: {e}")
            return False

    def get_camera_token(self, token: str):
        try:
            db = self._db()
            key = db.key("CameraToken", token)
            entity = db.get(key)
            if not entity:
                return None, None
            if time.time() > entity.get("expiry", 0):
                db.delete(key)
                return None, None
            return entity.get("user_id"), entity.get("expiry")
        except Exception as e:
            logger.error(f"Error retrieving camera token: {e}")
            return None, None

# Singleton instance
token_service = TokenService()
