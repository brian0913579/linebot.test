#!/bin/bash
cd ~/linebot.test
git pull origin main
sudo systemctl restart myapp
