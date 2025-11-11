#!/usr/bin/env python3
"""
Admin script to add authorized users to the database.

This script can add users to either MongoDB or SQLite depending on configuration.
It automatically falls back to SQLite if MongoDB is unavailable.

Usage:
    python add_user.py <user_id> <username>
    
Example:
    python add_user.py Uea6813ef8ec77e7446090621ebcf472a "John Doe"
"""

import sys
import os

# Add project root to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import add_user, remove_user, get_allowed_users, initialize_database


def print_usage():
    """Print usage instructions."""
    print("Usage:")
    print("  Add user:    python add_user.py add <user_id> <username>")
    print("  Remove user: python add_user.py remove <user_id>")
    print("  List users:  python add_user.py list")
    print()
    print("Examples:")
    print('  python add_user.py add Uea6813ef8ec77e7446090621ebcf472a "John Doe"')
    print("  python add_user.py remove Uea6813ef8ec77e7446090621ebcf472a")
    print("  python add_user.py list")


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    # Initialize database
    print("Initializing database connection...")
    try:
        db_mode = initialize_database()
        print(f"✓ Connected to database in {db_mode} mode")
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        sys.exit(1)
    
    if command == "add":
        # Add user
        if len(sys.argv) != 4:
            print("Error: 'add' command requires user_id and username")
            print_usage()
            sys.exit(1)
        
        user_id = sys.argv[2]
        username = sys.argv[3]
        
        print(f"\nAdding user: {user_id} ({username})...")
        success, message = add_user(user_id, username)
        
        if success:
            print(f"✓ {message}")
            sys.exit(0)
        else:
            print(f"✗ {message}")
            sys.exit(1)
    
    elif command == "remove":
        # Remove user
        if len(sys.argv) != 3:
            print("Error: 'remove' command requires user_id")
            print_usage()
            sys.exit(1)
        
        user_id = sys.argv[2]
        
        print(f"\nRemoving user: {user_id}...")
        success, message = remove_user(user_id)
        
        if success:
            print(f"✓ {message}")
            sys.exit(0)
        else:
            print(f"✗ {message}")
            sys.exit(1)
    
    elif command == "list":
        # List users
        print("\nRetrieving authorized users...")
        try:
            users = get_allowed_users()
            if users:
                print(f"\n✓ Found {len(users)} authorized user(s):")
                print("-" * 60)
                for user_id, username in users.items():
                    print(f"  {user_id:<35} {username}")
                print("-" * 60)
            else:
                print("✓ No authorized users found")
            sys.exit(0)
        except Exception as e:
            print(f"✗ Error retrieving users: {e}")
            sys.exit(1)
    
    else:
        print(f"Error: Unknown command '{command}'")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
