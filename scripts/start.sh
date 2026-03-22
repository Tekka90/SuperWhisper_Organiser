#!/bin/bash
# Simple startup script for SuperWhisper Organiser
# Run this manually or use it in a startup script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# Extract port from config.yaml if it exists
PORT=5000
if [ -f "$PROJECT_DIR/config.yaml" ]; then
    PORT=$(grep -A 2 "^web:" "$PROJECT_DIR/config.yaml" | grep "port:" | awk '{print $2}' | tr -d '"' | head -1)
    if [ -z "$PORT" ]; then
        PORT=5000
    fi
fi

echo "🎤 Starting SuperWhisper Organiser..."

# Check if already running
if pgrep -f "python[3]?.*sworganiser\.py.*(watch|web)" > /dev/null; then
    echo "⚠️  Service is already running"
    echo "Run scripts/stop.sh to stop it first"
    exit 1
fi

# Start the services in the background
cd "$PROJECT_DIR"

# Check if venv exists and is valid
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
if [ ! -f "$VENV_PYTHON" ] || ! "$VENV_PYTHON" --version &> /dev/null; then
    echo "  → Virtual environment is broken, recreating..."
    rm -rf venv
    python3 -m venv venv
    source venv/bin/activate
    echo "  → Installing dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo "  ✓ Virtual environment recreated"
else
    source venv/bin/activate
fi

# Use the venv's python explicitly
PYTHON="$PROJECT_DIR/venv/bin/python3"

echo "  → Starting watcher daemon..."
"$PYTHON" sworganiser.py watch >> "$LOG_DIR/watcher.log" 2>> "$LOG_DIR/watcher.error.log" &
WATCHER_PID=$!

sleep 2

echo "  → Starting web interface on http://localhost:$PORT..."
"$PYTHON" sworganiser.py web >> "$LOG_DIR/web.log" 2>> "$LOG_DIR/web.error.log" &
WEB_PID=$!

sleep 1

# Save PIDs for stop script
echo $WATCHER_PID > "$LOG_DIR/watcher.pid"
echo $WEB_PID > "$LOG_DIR/web.pid"

echo "✅ Services started!"
echo "   Watcher PID: $WATCHER_PID"
echo "   Web PID: $WEB_PID"
echo ""
echo "   Web Interface: http://localhost:$PORT"
echo "   Logs: $LOG_DIR/"
echo ""
echo "To stop: scripts/stop.sh"
