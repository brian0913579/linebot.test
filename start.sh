#!/bin/bash
python3 -m gunicorn -w 1 -b localhost:5000 app:app
