from google.cloud import datastore

# Global client to reuse connection
db = None

def get_datastore_client():
    global db
    if db is None:
        db = datastore.Client()
    return db

def get_allowed_users():
    """
    Fetches allowed users from Google Cloud Datastore.
    Kind: 'allowed_users'
    Key Name: user_id
    """
    try:
        db = get_datastore_client()
        query = db.query(kind='allowed_users')
        results = list(query.fetch())
        
        allowed_users = {}
        for entity in results:
            user_id = entity.get('user_id') or entity.key.name
            user_name = entity.get('user_name', 'Unknown')
            if user_id:
                allowed_users[user_id] = user_name
                
        return allowed_users
    except Exception as e:
        print(f"Error serving allowed_users from Datastore: {e}")
        return {}


def add_user(user_id, user_name):
    """Adds a user to Datastore."""
    import datetime
    try:
        db = get_datastore_client()
        key = db.key('allowed_users', user_id)
        entity = datastore.Entity(key=key)
        entity.update({
            'user_id': user_id,
            'user_name': user_name,
            'created_at': datetime.datetime.now(datetime.timezone.utc)
        })
        db.put(entity)
        return True
    except Exception as e:
        print(f"Error adding user {user_id}: {e}")
        return False


def remove_user(user_id):
    """Removes a user from Datastore."""
    try:
        db = get_datastore_client()
        key = db.key('allowed_users', user_id)
        db.delete(key)
        return True
    except Exception as e:
        print(f"Error removing user {user_id}: {e}")
        return False
