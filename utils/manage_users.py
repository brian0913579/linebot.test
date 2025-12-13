
import argparse
import sys
import os

from google.cloud import datastore
import datetime

def get_client():
    return datastore.Client()

def list_users():
    client = get_client()
    query = client.query(kind='allowed_users')
    results = list(query.fetch())
    
    print(f"\nFound {len(results)} users:")
    print("-" * 50)
    print(f"{'User ID':<40} | {'Name'}")
    print("-" * 50)
    for entity in results:
        uid = entity.get('user_id') or entity.key.name
        name = entity.get('user_name', 'Unknown')
        print(f"{uid:<40} | {name}")
    print("-" * 50)

def add_user(user_id, user_name):
    client = get_client()
    key = client.key('allowed_users', user_id)
    entity = datastore.Entity(key=key)
    entity.update({
        'user_id': user_id,
        'user_name': user_name,
        'created_at': datetime.datetime.now(datetime.timezone.utc)
    })
    client.put(entity)
    print(f"✅ Added user: {user_name} ({user_id})")

def remove_user(user_id):
    client = get_client()
    key = client.key('allowed_users', user_id)
    client.delete(key)
    print(f"✅ Removed user: {user_id}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage users in Google Cloud Datastore")
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # List
    subparsers.add_parser('list', help='List all users')

    # Add
    parser_add = subparsers.add_parser('add', help='Add a new user')
    parser_add.add_argument('user_id', help='LINE User ID')
    parser_add.add_argument('user_name', help='User Name')

    # Remove
    parser_remove = subparsers.add_parser('remove', help='Remove a user')
    parser_remove.add_argument('user_id', help='LINE User ID')

    args = parser.parse_args()

    try:
        if args.command == 'list':
            list_users()
        elif args.command == 'add':
            add_user(args.user_id, args.user_name)
        elif args.command == 'remove':
            remove_user(args.user_id)
        else:
            parser.print_help()
    except Exception as e:
        print(f"Error: {e}")
        print("Tip: Ensure you have set GOOGLE_APPLICATION_CREDENTIALS or run 'gcloud auth application-default login'")
