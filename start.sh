#!/bin/bash
# Activate virtual environment
source /home/cool_brian1206cool/linebot.test/venv/bin/activate

# Install dependencies if not already installed
pip install -r requirements.txt

# Start the app with gunicorn
venv/bin/python -m gunicorn -w 1 -b 127.0.0.1:8080 app:app
