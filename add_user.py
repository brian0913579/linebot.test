#!/usr/bin/env python3
"""
Add User Script

CLI utility to add authorized users to the MongoDB database.
This script allows administrators to add new users by their LINE user ID.

Usage:
    python add_user.py <line_user_id> <username>

Example:
    python add_user.py Uea6813ef8ec77e7446090621ebcf472a "Admin Brian"
"""

import argparse
import os
import sys

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.mongodb_client import (  # noqa: E402
    add_user,
    get_user,
    remove_user,
    update_user_authorization,
)


def main():
    parser = argparse.ArgumentParser(
        description="Manage authorized users in MongoDB database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Add a new user:
    python add_user.py add Uea6813ef8ec77e7446090621ebcf472a "Admin Brian"

  Check if a user exists:
    python add_user.py get Uea6813ef8ec77e7446090621ebcf472a

  Authorize an existing user:
    python add_user.py authorize Uea6813ef8ec77e7446090621ebcf472a

  Deauthorize a user:
    python add_user.py deauthorize Uea6813ef8ec77e7446090621ebcf472a

  Remove a user:
    python add_user.py remove Uea6813ef8ec77e7446090621ebcf472a
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Add user command
    add_parser = subparsers.add_parser("add", help="Add a new user")
    add_parser.add_argument(
        "line_user_id", help="LINE user ID (e.g., U1234567890abcdef)"
    )
    add_parser.add_argument("username", help="Display name for the user")
    add_parser.add_argument(
        "--unauthorized", action="store_true", help="Add user but mark as unauthorized"
    )

    # Get user command
    get_parser = subparsers.add_parser("get", help="Get user information")
    get_parser.add_argument("line_user_id", help="LINE user ID to look up")

    # Authorize user command
    auth_parser = subparsers.add_parser("authorize", help="Authorize an existing user")
    auth_parser.add_argument("line_user_id", help="LINE user ID to authorize")

    # Deauthorize user command
    deauth_parser = subparsers.add_parser("deauthorize", help="Deauthorize a user")
    deauth_parser.add_argument("line_user_id", help="LINE user ID to deauthorize")

    # Remove user command
    remove_parser = subparsers.add_parser("remove", help="Remove a user from database")
    remove_parser.add_argument("line_user_id", help="LINE user ID to remove")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "add":
            authorized = not args.unauthorized
            print(f"Adding user: {args.username} ({args.line_user_id})")
            print(f"Authorized: {authorized}")

            success = add_user(args.line_user_id, args.username, authorized)

            if success:
                print(f"✅ User {args.username} added successfully!")
                return 0
            else:
                print("❌ Failed to add user. User may already exist.")
                return 1

        elif args.command == "get":
            print(f"Looking up user: {args.line_user_id}")
            user = get_user(args.line_user_id)

            if user:
                print("\n✅ User found:")
                print(f"  LINE User ID: {user['line_user_id']}")
                print(f"  Username: {user['username']}")
                print(f"  Authorized: {user['authorized']}")
                if "added_at" in user:
                    print(f"  Added at: {user['added_at']}")
                return 0
            else:
                print(f"❌ User not found: {args.line_user_id}")
                return 1

        elif args.command == "authorize":
            print(f"Authorizing user: {args.line_user_id}")
            success = update_user_authorization(args.line_user_id, True)

            if success:
                print("✅ User authorized successfully!")
                return 0
            else:
                print("❌ Failed to authorize user. User may not exist.")
                return 1

        elif args.command == "deauthorize":
            print(f"Deauthorizing user: {args.line_user_id}")
            success = update_user_authorization(args.line_user_id, False)

            if success:
                print("✅ User deauthorized successfully!")
                return 0
            else:
                print("❌ Failed to deauthorize user. User may not exist.")
                return 1

        elif args.command == "remove":
            print(f"Removing user: {args.line_user_id}")

            # Confirm deletion
            confirm = input("Are you sure you want to remove this user? (yes/no): ")
            if confirm.lower() != "yes":
                print("❌ Operation cancelled.")
                return 0

            success = remove_user(args.line_user_id)

            if success:
                print("✅ User removed successfully!")
                return 0
            else:
                print("❌ Failed to remove user. User may not exist.")
                return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
