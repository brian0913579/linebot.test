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
