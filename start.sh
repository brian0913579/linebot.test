#!/bin/bash
# Set error handling
set -e

# Activate virtual environment
source /home/cool_brian1206cool/linebot.test/venv/bin/activate

# Install dependencies inside the virtual environment
echo "Installing dependencies (this may take a moment)..."
pip install -r requirements.txt > /dev/null 2>&1 || echo "Some dependencies could not be installed, but we'll try to run anyway."

# Set environment variables for logging
export LOG_LEVEL=INFO

# Start the app with gunicorn using the virtual environment's Python
echo "Starting LineBot application..."
venv/bin/python -m gunicorn -w 1 -b 127.0.0.1:8080 app:app --log-level warning
