#!/bin/bash
# Set error handling
set -e

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"
ACTIVATE_PATH="$VENV_DIR/bin/activate"

# Make sure all scripts are executable
chmod +x "$PROJECT_ROOT/scripts/"*.sh

# Check if virtual environment exists, if not create it
if [ ! -f "$ACTIVATE_PATH" ]; then
    echo "Virtual environment not found, creating one..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$ACTIVATE_PATH"

# Install dependencies inside the virtual environment
echo "Installing dependencies (this may take a moment)..."
pip install -r "$PROJECT_ROOT/requirements.txt" || echo "Some dependencies could not be installed, but we'll try to run anyway."

# Set environment variables for logging
export LOG_LEVEL=INFO

# Start the app with gunicorn using the virtual environment's Python
echo "Starting LineBot application..."
cd "$PROJECT_ROOT"
python -m gunicorn -w 1 -b 127.0.0.1:8080 app:app --log-level warning
