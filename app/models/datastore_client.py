import datetime

from google.cloud import datastore

from utils.logger_config import get_logger

logger = get_logger(__name__)

_db = None


def get_datastore_client():
    global _db
    if _db is None:
        _db = datastore.Client()
    return _db


def get_allowed_users():
    """Fetches allowed users from Google Cloud Datastore."""
    try:
        db = get_datastore_client()
        query = db.query(kind="allowed_users")
        results = list(query.fetch())

        allowed_users = {}
        for entity in results:
            user_id = entity.get("user_id") or entity.key.name
            user_name = entity.get("user_name", "Unknown")
            if user_id:
                allowed_users[user_id] = user_name

        return allowed_users
    except Exception as e:
        print(f"Error serving allowed_users from Datastore: {e}")
        return {}


def add_user(user_id, user_name):
    """Adds a user to Datastore."""
    try:
        db = get_datastore_client()
        key = db.key("allowed_users", user_id)
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "user_id": user_id,
                "user_name": user_name,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
        db.put(entity)
        return True
    except Exception as e:
        print(f"Error adding user {user_id}: {e}")
        return False


def remove_user(user_id):
    """
    Remove a user from the allowed list.
    Args:
        user_id (str): The ID of the user to remove.
    """
    db = get_datastore_client()
    if not db:
        return False
    key = db.key("AllowedUser", user_id)
    db.delete(key)
    logger.info(f"Removed user {user_id} from allowed users in Datastore.")
    return True


# ==========================================
# Audit Logging
# ==========================================
def log_admin_action(admin_username, action, target_user_id, metadata=None):
    """
    Log an administrative action to Datastore for auditing.
    """
    db = get_datastore_client()
    if not db:
        return False

    try:
        from datetime import datetime, timezone

        key = db.key("AuditLog")
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "admin_username": admin_username,
                "action": action,
                "target_user_id": target_user_id,
                "metadata": metadata or {},
                "timestamp": datetime.now(timezone.utc),
            }
        )
        db.put(entity)
        logger.info(f"Audit log saved: {admin_username} {action} {target_user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to save audit log: {str(e)}")
        return False


def get_pending_users():
    """Fetches pending users from Google Cloud Datastore."""
    try:
        db = get_datastore_client()
        query = db.query(kind="pending_users")
        results = list(query.fetch())

        pending_users = {}
        for entity in results:
            user_id = entity.get("user_id") or entity.key.name
            user_name = entity.get("user_name", "Unknown")
            if user_id:
                pending_users[user_id] = user_name

        return pending_users
    except Exception as e:
        print(f"Error serving pending_users from Datastore: {e}")
        return {}


def add_pending_user(user_id, user_name="Unknown"):
    """Adds a pending user to Datastore."""
    try:
        db = get_datastore_client()
        key = db.key("pending_users", user_id)

        existing = db.get(key)
        if existing:
            return True

        entity = datastore.Entity(key=key)
        entity.update(
            {
                "user_id": user_id,
                "user_name": user_name,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
        db.put(entity)
        return True
    except Exception as e:
        print(f"Error adding pending user {user_id}: {e}")
        return False


def remove_pending_user(user_id):
    """Removes a user from pending_users Datastore."""
    try:
        db = get_datastore_client()
        key = db.key("pending_users", user_id)
        db.delete(key)
        return True
    except Exception as e:
        print(f"Error removing pending user {user_id}: {e}")
        return False
