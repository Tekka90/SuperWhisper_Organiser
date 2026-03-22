#!/bin/bash
# Start script for SuperWhisper Organiser service
# Runs both the watcher (daemon) and web interface

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
MAIN_PY="$PROJECT_DIR/sworganiser.py"

# Function to cleanup on exit
cleanup() {
    echo "Stopping services..."
    if [ ! -z "$WATCHER_PID" ]; then
        kill $WATCHER_PID 2>/dev/null || true
    fi
    if [ ! -z "$WEB_PID" ]; then
        kill $WEB_PID 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGTERM SIGINT

# Start the watcher in the background
echo "Starting watcher daemon..."
"$VENV_PYTHON" "$MAIN_PY" watch &
WATCHER_PID=$!
echo "Watcher started with PID: $WATCHER_PID"

# Give it a moment to initialize
sleep 2

# Start the web interface in the background
echo "Starting web interface..."
"$VENV_PYTHON" "$MAIN_PY" web &
WEB_PID=$!
echo "Web interface started with PID: $WEB_PID"

# Wait for both processes
wait
