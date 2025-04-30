def insert_user(user_id, user_name):
    connection = sqlite3.connect('users.db')  # Connect to the database
    cursor = connection.cursor()
    cursor.execute('''
    INSERT INTO allowed_users (user_id, user_name) VALUES (?, ?)
    ''', (user_id, user_name))  # Insert user ID and user name
    connection.commit()  # Save changes
    connection.close()  # Close the connection

# Example usage to insert users:
insert_user('Uea6813ef8ec77e7446090621ebcf472a', 'admin_Brian')
insert_user('U1d640cea545510e631396b5306ade151', 'cyn.18')