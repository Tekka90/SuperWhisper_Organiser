#!/bin/bash
# Quick Start Script for SuperWhisper Organiser v2.0

# Change to project root (script lives in scripts/ subfolder)
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

# Change to project root (script lives in scripts/ subfolder)
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/..

echo "🎙️  SuperWhisper Organiser v2.0 Setup"
echo "======================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Available commands:"
echo "  python sworganiser.py web          - Start web interface"
echo "  python sworganiser.py watch        - Monitor for new recordings"
echo "  python sworganiser.py process-all  - Process existing recordings"
echo "  python sworganiser.py scan-notes   - Scan notes for learning"
echo ""
echo "🌐 To start the web interface, run:"
echo "   python sworganiser.py web"
echo ""
echo "Then visit: http://127.0.0.1:5000"
echo ""
