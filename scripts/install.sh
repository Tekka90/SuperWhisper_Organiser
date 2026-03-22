#!/bin/bash
# Installation script for SuperWhisper Organiser
# Sets up the application and creates a macOS LaunchAgent service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🎤 SuperWhisper Organiser - Installation${NC}"
echo "=========================================="
echo ""

# Get the absolute path of the installation directory
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPTS_DIR")"
SERVICE_NAME="com.superwhisper.organiser"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

echo -e "${BLUE}Installation directory:${NC} $INSTALL_DIR"
echo ""

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

# Check macOS version
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}❌ Error: This script is for macOS only${NC}"
    exit 1
fi

OS_VERSION=$(sw_vers -productVersion)
echo -e "${GREEN}✓${NC} macOS version: $OS_VERSION"

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: Python 3 is not installed${NC}"
    echo -e "${YELLOW}Please install Python 3.8 or higher:${NC}"
    echo "  brew install python@3.11"
    echo "  or download from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PYTHON_PATH=$(which python3)
VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION found at $PYTHON_PATH"

# Check Python version is >= 3.8
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${RED}❌ Error: Python 3.8 or higher is required${NC}"
    echo "   Current version: $PYTHON_VERSION"
    exit 1
fi

# Check pip
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${RED}❌ Error: pip is not installed${NC}"
    echo -e "${YELLOW}Installing pip...${NC}"
    python3 -m ensurepip --upgrade
fi
echo -e "${GREEN}✓${NC} pip is available"

# Check if config.yaml exists
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    echo -e "${RED}❌ Error: config.yaml not found${NC}"
    echo -e "${YELLOW}Please create config.yaml from config.example.yaml${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} config.yaml found"

echo ""

# Create virtual environment
echo -e "${BLUE}Setting up virtual environment...${NC}"
if [ -d "$INSTALL_DIR/venv" ]; then
    # Check if the venv Python is valid
    if [ ! -f "$INSTALL_DIR/venv/bin/python3" ] || ! "$INSTALL_DIR/venv/bin/python3" --version &> /dev/null; then
        echo -e "${YELLOW}⚠️  Existing virtual environment is broken, recreating...${NC}"
        rm -rf "$INSTALL_DIR/venv"
        python3 -m venv "$INSTALL_DIR/venv"
        echo -e "${GREEN}✓${NC} Virtual environment recreated"
    else
        echo -e "${GREEN}✓${NC} Virtual environment already exists and is valid"
    fi
else
    echo "Creating virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
    echo -e "${GREEN}✓${NC} Virtual environment created"
fi

# Activate virtual environment and install dependencies
echo "Installing dependencies in virtual environment..."
source "$INSTALL_DIR/venv/bin/activate"

# Upgrade pip
echo "  → Upgrading pip..."
pip install --upgrade pip --quiet

# Install requirements
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    echo "  → Installing required packages..."
    if pip install -r "$INSTALL_DIR/requirements.txt" --quiet; then
        echo -e "${GREEN}✓${NC} Dependencies installed"
    else
        echo -e "${YELLOW}⚠️  Some packages may have warnings, but installation continued${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  requirements.txt not found, skipping pip install${NC}"
fi

echo ""

# Check for OpenAI API key
echo -e "${BLUE}Checking OpenAI API configuration...${NC}"
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  OpenAI API key not found in environment${NC}"
    echo "   Add it to config.yaml or set OPENAI_API_KEY environment variable"
else
    echo -e "${GREEN}✓${NC} OpenAI API key found in environment"
fi

echo ""

# Create logs directory
mkdir -p "$INSTALL_DIR/logs"

# Make management scripts executable
chmod +x "$SCRIPTS_DIR/start.sh" "$SCRIPTS_DIR/stop.sh" "$SCRIPTS_DIR/status.sh" 2>/dev/null || true

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo -e "${BLUE}To start the services:${NC}"
echo "  scripts/start.sh"
echo ""
echo -e "${BLUE}To check status:${NC}"
echo "  scripts/status.sh"
echo ""
echo -e "${BLUE}To stop services:${NC}"
echo "  scripts/stop.sh"
echo ""
echo -e "${BLUE}Services:${NC}"
echo "  ✓ Watcher: Monitors for new recordings"
echo "  ✓ Web Interface: http://localhost:5000"
echo ""
echo -e "${BLUE}Logs:${NC}"
echo "  Location: $INSTALL_DIR/logs/"
echo "  View:     tail -f logs/web.log logs/watcher.log"
echo "  Errors:   tail -f logs/web.error.log logs/watcher.error.log"
echo ""
echo -e "${BLUE}Virtual Environment:${NC}"
echo "  Python: $VENV_PYTHON"
echo "  Activate: source $INSTALL_DIR/venv/bin/activate"
echo ""
echo -e "${YELLOW}Note:${NC} Services don't start automatically on login."
echo "Run scripts/start.sh manually or add it to your startup items."
echo ""
