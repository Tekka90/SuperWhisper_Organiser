#!/bin/bash
# Uninstallation script for SuperWhisper Organiser
# Removes the macOS LaunchAgent service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🎤 SuperWhisper Organiser - Uninstall${NC}"
echo "=========================================="
echo ""

SERVICE_NAME="com.superwhisper.organiser"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

# Check if service exists
if [ ! -f "$PLIST_PATH" ]; then
    echo -e "${YELLOW}⚠️  Service not found at: $PLIST_PATH${NC}"
    echo "Service may not be installed or already removed."
    exit 0
fi

echo -e "${BLUE}This will:${NC}"
echo "  1. Stop the SuperWhisper Organiser service"
echo "  2. Unload it from LaunchAgents"
echo "  3. Remove the plist file"
echo ""
echo -e "${YELLOW}Note: This will NOT delete:${NC}"
echo "  - Your notes and recordings"
echo "  - The application code"
echo "  - Configuration files"
echo "  - Database files"
echo ""

read -p "Continue with uninstallation? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

echo ""
echo -e "${BLUE}Uninstalling service...${NC}"

# Stop and unload the service
if launchctl list | grep -q "$SERVICE_NAME"; then
    echo -e "${BLUE}Stopping service...${NC}"
    
    # Try modern launchctl command first
    if launchctl bootout "gui/$(id -u)/$SERVICE_NAME" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Service stopped (bootout)"
    else
        # Fallback to older command
        if launchctl unload "$PLIST_PATH" 2>/dev/null; then
            echo -e "${GREEN}✓${NC} Service stopped (unload)"
        else
            echo -e "${YELLOW}⚠️  Could not stop service, but will continue${NC}"
        fi
    fi
else
    echo -e "${YELLOW}⚠️  Service not running${NC}"
fi

# Remove the plist file
if [ -f "$PLIST_PATH" ]; then
    rm "$PLIST_PATH"
    echo -e "${GREEN}✓${NC} Removed plist file"
else
    echo -e "${YELLOW}⚠️  Plist file already removed${NC}"
fi

# Verify removal
sleep 1
if launchctl list | grep -q "$SERVICE_NAME"; then
    echo -e "${YELLOW}⚠️  Service may still be running. Try logging out and back in.${NC}"
else
    echo -e "${GREEN}✓${NC} Service completely removed"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Uninstallation complete!${NC}"
echo ""
echo -e "${BLUE}Optional cleanup:${NC}"
echo ""

# Ask if user wants to remove venv
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$INSTALL_DIR/venv" ]; then
    read -p "Do you want to remove the virtual environment? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR/venv"
        echo -e "${GREEN}✓${NC} Virtual environment removed"
    else
        echo -e "${BLUE}ℹ${NC}  Virtual environment kept at: $INSTALL_DIR/venv"
    fi
    echo ""
fi

echo -e "${BLUE}To completely remove the application:${NC}"
echo "  1. Delete the application directory"
if [ -d "$INSTALL_DIR/venv" ]; then
    echo "  2. Remove the virtual environment: rm -rf $INSTALL_DIR/venv"
fi
echo "  3. Optionally delete your notes and database"
echo ""
echo -e "${BLUE}To reinstall:${NC}"
echo "  Run: bash install.sh"
echo ""
