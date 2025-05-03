#!/bin/bash
source /home/cool_brian1206cool/linebot.test/venv/bin/activate
python3 -m gunicorn -w 1 -b 127.0.0.1:8080 app:app
