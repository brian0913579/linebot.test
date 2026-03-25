import json
import secrets as py_secrets
import time

from google.cloud import datastore
from flask import current_app

from utils.logger_config import get_logger

logger = get_logger(__name__)


class TokenService:
    def __init__(self, app=None):
        self._ds_client = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the Datastore client."""
        try:
            self._ds_client = datastore.Client()
            logger.info("Datastore client initialized for TokenService")
        except Exception as e:
            logger.error(f"Failed to initialize Datastore client: {e}")

    def _db(self):
        if self._ds_client is None:
            try:
                self._ds_client = datastore.Client()
            except Exception as e:
                logger.error(f"Failed to lazy-init Datastore client: {e}")
        return self._ds_client

    # ------------------------------------------------------------------
    # Verify tokens  (one-time use, consumed on first read)
    # ------------------------------------------------------------------

    def store_verify_token(self, token: str, user_id: str, action: str = None) -> bool:
        expiry = time.time() + current_app.config["VERIFY_TTL"]
        try:
            db = self._db()
            key = db.key("VerifyToken", token)
            entity = datastore.Entity(key=key)
            entity.update({"user_id": user_id, "expiry": expiry, "action": action})
            db.put(entity)
            return True
        except Exception as e:
            logger.error(f"Error storing verify token: {e}")
            return False

    def get_verify_token(self, token: str):
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

    # ------------------------------------------------------------------
    # Action tokens  (open / close)
    # ------------------------------------------------------------------

    def store_action_token(self, token: str, user_id: str, action: str) -> bool:
        expiry = time.time() + current_app.config["VERIFY_TTL"]
        try:
            db = self._db()
            key = db.key("ActionToken", token)
            entity = datastore.Entity(key=key)
            entity.update({"user_id": user_id, "action": action, "expiry": expiry})
            db.put(entity)
            return True
        except Exception as e:
            logger.error(f"Error storing action token: {e}")
            return False

    def get_action_token(self, token: str):
        try:
            db = self._db()
            key = db.key("ActionToken", token)
            entity = db.get(key)
            if not entity:
                return None, None, None
            db.delete(key)
            if time.time() > entity.get("expiry", 0):
                return None, None, None
            return entity.get("user_id"), entity.get("action"), entity.get("expiry")
        except Exception as e:
            logger.error(f"Error retrieving action token: {e}")
            return None, None, None

    def invalidate_user_tokens(self, user_id: str) -> None:
        try:
            db = self._db()
            query = db.query(kind="ActionToken")
            for entity in query.fetch():
                if entity.get("user_id") == user_id:
                    db.delete(entity.key)
        except Exception as e:
            logger.error(f"Error invalidating user tokens: {e}")

    # ------------------------------------------------------------------
    # Camera tokens
    # ------------------------------------------------------------------

    def store_camera_token(self, token: str, user_id: str) -> bool:
        expiry = time.time() + current_app.config["CAMERA_TOKEN_TTL"]
        try:
            db = self._db()
            key = db.key("CameraToken", token)
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def generate_token(self, user_id: str):
        """Return a (open_token, close_token) pair."""
        return py_secrets.token_urlsafe(16), py_secrets.token_urlsafe(16)


# Singleton instance
token_service = TokenService()
