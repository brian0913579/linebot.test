import importlib.util
import json
import secrets as py_secrets
import time

from flask import current_app
from google.cloud import datastore

from utils.logger_config import get_logger

logger = get_logger(__name__)

redis_installed = importlib.util.find_spec("redis") is not None
if redis_installed:
    from redis import Redis
    from redis.exceptions import RedisError
else:

    class Redis:
        pass

    class RedisError(Exception):
        pass


class TokenService:
    def __init__(self, app=None):
        self.redis_client = None
        self._ds_client = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize Redis client if available."""
        if redis_installed:
            try:
                self.redis_client = Redis(
                    host=app.config["REDIS_HOST"],
                    port=app.config["REDIS_PORT"],
                    db=app.config["REDIS_DB"],
                    password=app.config["REDIS_PASSWORD"],
                    ssl=app.config["REDIS_SSL"],
                    socket_timeout=3,
                    socket_connect_timeout=3,
                    decode_responses=True,
                )
                self.redis_client.ping()
                logger.info("Successfully connected to Redis server")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                self.redis_client = None
        else:
            logger.warning("Redis not installed, relying on Google Cloud Datastore")

    def get_ds_client(self):
        """Lazy load Google Cloud Datastore client for cross-instance fallback."""
        if self._ds_client is None:
            try:
                self._ds_client = datastore.Client()
            except Exception as e:
                logger.error(f"Failed to initialize Datastore fallback client: {e}")
        return self._ds_client

    def store_verify_token(self, token, user_id):
        expiry = time.time() + current_app.config["VERIFY_TTL"]
        try:
            if self.redis_client:
                data = json.dumps({"user_id": user_id, "expiry": expiry})
                return self.redis_client.setex(
                    f"verify_token:{token}", current_app.config["VERIFY_TTL"], data
                )

            logger.warning(
                "Redis unavailable for storing verify token, using Datastore fallback"
            )
            db = self.get_ds_client()
            if db:
                key = db.key("VerifyToken", token)
                entity = datastore.Entity(key=key)
                entity.update({"user_id": user_id, "expiry": expiry})
                db.put(entity)
            return True
        except RedisError as e:
            logger.error(f"Redis error while storing verify token: {str(e)}")
            return False

    def get_verify_token(self, token):
        try:
            if self.redis_client:
                key = f"verify_token:{token}"
                data = self.redis_client.get(key)
                if not data:
                    return None, None

                parsed = json.loads(data)
                self.redis_client.delete(key)

                if time.time() > parsed.get("expiry", 0):
                    return None, None
                return parsed.get("user_id"), parsed.get("expiry")

            db = self.get_ds_client()
            if db:
                key = db.key("VerifyToken", token)
                entity = db.get(key)
                if entity:
                    db.delete(key)
                    if time.time() > entity.get("expiry", 0):
                        return None, None
                    return entity.get("user_id"), entity.get("expiry")
            return None, None
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error retrieving verify token: {str(e)}")
            return None, None

    def authorize_user(self, user_id):
        expiry = time.time() + current_app.config["LOCATION_TTL"]
        try:
            if self.redis_client:
                return self.redis_client.setex(
                    f"auth_user:{user_id}", current_app.config["LOCATION_TTL"], expiry
                )

            db = self.get_ds_client()
            if db:
                key = db.key("AuthUser", user_id)
                entity = datastore.Entity(key=key)
                entity.update({"expiry": expiry})
                db.put(entity)
            return True
        except RedisError as e:
            logger.error(f"Redis error while authorizing user: {str(e)}")
            return False

    def is_user_authorized(self, user_id):
        try:
            if self.redis_client:
                expiry_str = self.redis_client.get(f"auth_user:{user_id}")
                if not expiry_str:
                    return False
                try:
                    return time.time() <= float(expiry_str)
                except ValueError:
                    return False

            db = self.get_ds_client()
            if db:
                key = db.key("AuthUser", user_id)
                entity = db.get(key)
                if entity:
                    return time.time() <= float(entity.get("expiry", 0))
            return False
        except RedisError as e:
            logger.error(f"Redis error checking user authorization: {str(e)}")
            return False

    def store_action_token(self, token, user_id, action):
        expiry = time.time() + current_app.config["VERIFY_TTL"]
        data = json.dumps({"user_id": user_id, "action": action, "expiry": expiry})
        try:
            if self.redis_client:
                return self.redis_client.setex(
                    f"action_token:{token}", current_app.config["VERIFY_TTL"], data
                )

            db = self.get_ds_client()
            if db:
                key = db.key("ActionToken", token)
                entity = datastore.Entity(key=key)
                entity.update({"user_id": user_id, "action": action, "expiry": expiry})
                db.put(entity)
            return True
        except RedisError as e:
            logger.error(f"Redis error while storing action token: {str(e)}")
            return False

    def get_action_token(self, token):
        try:
            if self.redis_client:
                data = self.redis_client.get(f"action_token:{token}")
                if not data:
                    return None, None, None

                parsed = json.loads(data)
                self.redis_client.delete(f"action_token:{token}")

                if time.time() > parsed.get("expiry", 0):
                    return None, None, None
                return parsed.get("user_id"), parsed.get("action"), parsed.get("expiry")

            db = self.get_ds_client()
            if db:
                key = db.key("ActionToken", token)
                entity = db.get(key)
                if entity:
                    db.delete(key)
                    if time.time() > entity.get("expiry", 0):
                        return None, None, None
                    return (
                        entity.get("user_id"),
                        entity.get("action"),
                        entity.get("expiry"),
                    )
            return None, None, None
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error retrieving action token: {str(e)}")
            return None, None, None

    def generate_token(self, user_id):
        token_open = py_secrets.token_urlsafe(16)
        token_close = py_secrets.token_urlsafe(16)
        return token_open, token_close

    def invalidate_user_tokens(self, user_id: str) -> None:
        if not self.redis_client:
            db = self.get_ds_client()
            if db:
                query = db.query(kind="ActionToken")
                for entity in query.fetch():
                    if entity.get("user_id") == user_id:
                        db.delete(entity.key)
            return

        try:
            keys_to_delete = []
            for key in self.redis_client.scan_iter("action_token:*"):
                data = self.redis_client.get(key)
                if data:
                    parsed = json.loads(data)
                    if parsed.get("user_id") == user_id:
                        keys_to_delete.append(key)
            if keys_to_delete:
                self.redis_client.delete(*keys_to_delete)
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error invalidating user tokens: {str(e)}")


# Create a singleton instance
token_service = TokenService()
