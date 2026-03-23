#!/bin/bash
# Stop script for SuperWhisper Organiser

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RUN_DIR="$PROJECT_DIR/run"

echo "🛑 Stopping SuperWhisper Organiser..."

# Try to stop using saved PIDs first
if [ -f "$RUN_DIR/watcher.pid" ]; then
    WATCHER_PID=$(cat "$RUN_DIR/watcher.pid")
    if kill -0 $WATCHER_PID 2>/dev/null; then
        kill $WATCHER_PID
        echo "  ✓ Stopped watcher (PID: $WATCHER_PID)"
    fi
    rm -f "$RUN_DIR/watcher.pid"
fi

if [ -f "$RUN_DIR/web.pid" ]; then
    WEB_PID=$(cat "$RUN_DIR/web.pid")
    if kill -0 $WEB_PID 2>/dev/null; then
        kill $WEB_PID
        echo "  ✓ Stopped web interface (PID: $WEB_PID)"
    fi
    rm -f "$RUN_DIR/web.pid"
fi

# Fallback: find and kill any remaining processes
PIDS=$(pgrep -if "python[3]?.*sworganiser\.py.*(watch|web)")
if [ ! -z "$PIDS" ]; then
    echo "  → Cleaning up remaining processes..."
    kill $PIDS 2>/dev/null || true
    sleep 1
    # Force kill if still running
    pkill -9 -if "python[3]?.*sworganiser\.py.*(watch|web)" 2>/dev/null || true
fi

echo "✅ Services stopped"
