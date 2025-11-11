"""
createUserDatabase.py

This module initializes the user database by creating the users.db SQLite database
and setting up the allowed_users table with columns user_id and user_name.
"""

# pylint: disable=invalid-name

import sqlite3


def create_db():
    """
    Creates the users.db SQLite database and sets up the allowed_users table.
    """

    connection = sqlite3.connect(
        "users.db"
    )  # Connects to the database (creates it if it doesn't exist)
    cursor = connection.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS allowed_users (
        user_id TEXT PRIMARY KEY,
        user_name TEXT
    );
    """
    )
    connection.commit()  # Save changes
    connection.close()  # Close the connection


create_db()  # Call this function once to create the database and table
