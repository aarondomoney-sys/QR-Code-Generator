#!/usr/bin/env bash
# Starts the app AND creates a public URL you can send to anyone by email.
# First run: brew install ngrok/ngrok/ngrok  (done automatically below)

set -e
cd "$(dirname "$0")"

# Install ngrok if missing
if ! command -v ngrok &>/dev/null; then
  echo "Installing ngrok..."
  brew install ngrok/ngrok/ngrok
fi

# Start the Flask app in the background if not already running
if ! lsof -i :8080 &>/dev/null; then
  echo "Starting Hugo Cars QR app..."
  python3 app.py &
  sleep 2
fi

echo ""
echo "App is running. Creating public URL..."
echo "Copy the https:// URL below and send it to your coworkers."
echo "──────────────────────────────────────────────────────"
ngrok http 8080
