# LineBot Test

This repository contains the code for a LineBot service, developed as a test application. The bot is used to interact with users, validate parking lot access, and handle various user requests using the Line messaging platform.

## Features

- User authentication and authorization
- GPS-based location checks
- Token-based access control for opening/closing the gate
- Error handling and logging

## Setup and Installation

### Prerequisites

- Python 3.x
- pip (Python package manager)
- SQLite (for storing user information)

### Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/linebot.test.git
   cd linebot.test
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up the environment variables:
   Create a `.env` file in the root directory and add the following:
   ```env
   LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token
   LINE_CHANNEL_SECRET=your_channel_secret
   ```

4. Create the SQLite database:
   Run the script `create_db.py` to set up the `users.db` database and `allowed_users` table.

   ```bash
   python create_db.py
   ```

5. Start the server:
   ```bash
   python app.py
   ```

## Usage

- The bot listens for messages and performs operations like checking user permissions, validating parking lot access, and opening/closing the gate based on token-based commands.

- Users interact with the bot via text and location messages, and the bot responds accordingly.

## Error Handling

The application provides detailed error logs if any unexpected errors occur. For example, if an unauthorized user tries to use the service, they will receive an error message explaining the issue.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.