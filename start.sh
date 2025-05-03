#!/bin/bash
python3 -m gunicorn -w 1 -b 127.0.0.1:8080 app:app
