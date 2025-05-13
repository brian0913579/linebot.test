import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "/tmp/users.db")


def get_allowed_users():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    cursor.execute("SELECT user_id, user_name FROM allowed_users")
    users = cursor.fetchall()
    connection.close()
    return {user[0]: user[1] for user in users}
