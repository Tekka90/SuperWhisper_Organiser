#!/bin/bash
# Setup script for SuperWhisper Organiser

set -e

# Change to project root (script lives in scripts/ subfolder)
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

# Change to project root (script lives in scripts/ subfolder)
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/..


echo "🎤 SuperWhisper Organiser - Setup"
echo "=================================="
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Found Python $PYTHON_VERSION"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip > /dev/null
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Create config if it doesn't exist
if [ ! -f "config.yaml" ]; then
    echo "Creating config.yaml from template..."
    cp config.example.yaml config.yaml
    echo "✓ Config file created"
    echo ""
    echo "⚠️  Please edit config.yaml to set your OpenAI API key and paths"
else
    echo "✓ Config file already exists"
fi
echo ""

# Create notes directory
if [ ! -d "notes" ]; then
    mkdir -p notes
    echo "✓ Notes directory created"
fi
echo ""

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OpenAI API key not found in environment"
    echo "Please set it in one of these ways:"
    echo "  1. Export: export OPENAI_API_KEY='your-key-here'"
    echo "  2. Edit config.yaml and set openai.api_key"
    echo "  3. Create .env file with OPENAI_API_KEY=your-key-here"
else
    echo "✓ OpenAI API key found in environment"
fi
echo ""

echo "=================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Configure: nano config.yaml"
echo "  2. Set API key: export OPENAI_API_KEY='your-key'"
echo "  3. Test: source venv/bin/activate && python sworganiser.py --help"
echo "  4. Run: python sworganiser.py --daemon"
echo ""
echo "For more information, see README.md"
