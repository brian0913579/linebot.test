import datetime

from google.cloud import datastore

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
    """Removes a user from Datastore."""
    try:
        db = get_datastore_client()
        key = db.key("allowed_users", user_id)
        db.delete(key)
        return True
    except Exception as e:
        print(f"Error removing user {user_id}: {e}")
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
