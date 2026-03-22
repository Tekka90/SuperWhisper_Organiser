#!/bin/bash
# Check status of SuperWhisper Organiser services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

# Extract port from config.yaml if it exists
PORT=5000
if [ -f "$PROJECT_DIR/config.yaml" ]; then
    PORT=$(grep -A 2 "^web:" "$PROJECT_DIR/config.yaml" | grep "port:" | awk '{print $2}' | tr -d '"' | head -1)
    if [ -z "$PORT" ]; then
        PORT=5000
    fi
fi

echo "🎤 SuperWhisper Organiser Status"
echo "=================================="
echo ""

# Check for running processes - try PID files first (most reliable), then case-insensitive pgrep
WATCHER_PIDS=""
WEB_PIDS=""

if [ -f "$LOG_DIR/watcher.pid" ]; then
    PID=$(cat "$LOG_DIR/watcher.pid" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        WATCHER_PIDS=$PID
    fi
fi

if [ -f "$LOG_DIR/web.pid" ]; then
    PID=$(cat "$LOG_DIR/web.pid" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        WEB_PIDS=$PID
    fi
fi

# Fallback: case-insensitive pgrep (handles Python vs python3 binary naming)
if [ -z "$WATCHER_PIDS" ]; then
    WATCHER_PIDS=$(pgrep -if "python.*sworganiser\.py.*watch" 2>/dev/null)
fi
if [ -z "$WEB_PIDS" ]; then
    WEB_PIDS=$(pgrep -if "python.*sworganiser\.py.*web" 2>/dev/null)
fi

if [ ! -z "$WATCHER_PIDS" ]; then
    echo "✅ Watcher: Running (PID: $WATCHER_PIDS)"
else
    echo "❌ Watcher: Not running"
fi

if [ ! -z "$WEB_PIDS" ]; then
    echo "✅ Web Interface: Running (PID: $WEB_PIDS)"
    echo "   URL: http://localhost:$PORT"
else
    echo "❌ Web Interface: Not running"
fi

echo ""

# Show recent logs if services are running
if [ ! -z "$WATCHER_PIDS" ] || [ ! -z "$WEB_PIDS" ]; then
    echo "Recent Activity:"
    echo "----------------"
    
    if [ -f "$LOG_DIR/watcher.log" ]; then
        echo ""
        echo "Watcher (last 5 lines):"
        tail -5 "$LOG_DIR/watcher.log" 2>/dev/null || echo "  No logs yet"
    fi
    
    if [ -f "$LOG_DIR/web.log" ]; then
        echo ""
        echo "Web Interface (last 5 lines):"
        tail -5 "$LOG_DIR/web.log" 2>/dev/null || echo "  No logs yet"
    fi
    
    # Check for actual errors (WARNING/ERROR level lines only)
    if [ -f "$LOG_DIR/watcher.error.log" ]; then
        ERROR_LINES=$(grep -E " - (ERROR|WARNING) - " "$LOG_DIR/watcher.error.log" 2>/dev/null | tail -5)
        if [ -n "$ERROR_LINES" ]; then
            echo ""
            echo "⚠️  Watcher Warnings/Errors:"
            echo "$ERROR_LINES"
        fi
    fi
    
    if [ -f "$LOG_DIR/web.error.log" ]; then
        ERROR_LINES=$(grep -E " - (ERROR|WARNING) - " "$LOG_DIR/web.error.log" 2>/dev/null | tail -5)
        if [ -n "$ERROR_LINES" ]; then
            echo ""
            echo "⚠️  Web Interface Warnings/Errors:"
            echo "$ERROR_LINES"
        fi
    fi
fi

echo ""
echo "Commands:"
echo "  Start:  scripts/start.sh"
echo "  Stop:   scripts/stop.sh"
echo "  Status: scripts/status.sh"
echo ""
