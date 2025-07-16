#!/bin/bash
# setup_cron.sh - Interactive script to set up cron jobs for the web scraper

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
VENV_DIR="$PROJECT_DIR/venv"
MAIN_SCRIPT="$PROJECT_DIR/src/main.py"

echo -e "${GREEN}Web Scraper Cron Setup${NC}"
echo "=============================="
echo "Project directory: $PROJECT_DIR"
echo

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}Error: Virtual environment not found at $VENV_DIR${NC}"
    echo "Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Check if main script exists
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo -e "${RED}Error: Main script not found at $MAIN_SCRIPT${NC}"
    exit 1
fi

# Check if wrapper script exists
WRAPPER_SCRIPT="$SCRIPTS_DIR/cron_wrapper.sh"
if [ ! -f "$WRAPPER_SCRIPT" ]; then
    echo -e "${RED}Error: Wrapper script not found at $WRAPPER_SCRIPT${NC}"
    echo "Please run this script after creating cron_wrapper.sh"
    exit 1
fi

echo -e "${YELLOW}Available scheduling options:${NC}"
echo "1. Every 6 hours (0 */6 * * *)"
echo "2. Twice daily at 9 AM and 9 PM (0 9,21 * * *)"
echo "3. Daily at 2 AM (0 2 * * *)"
echo "4. Every 2 hours during business hours (0 8-18/2 * * *)"
echo "5. Custom schedule"
echo

read -p "Select scheduling option (1-5): " schedule_option

case $schedule_option in
    1)
        CRON_SCHEDULE="0 */6 * * *"
        SCHEDULE_DESC="every 6 hours"
        ;;
    2)
        CRON_SCHEDULE="0 9,21 * * *"
        SCHEDULE_DESC="twice daily at 9 AM and 9 PM"
        ;;
    3)
        CRON_SCHEDULE="0 2 * * *"
        SCHEDULE_DESC="daily at 2 AM"
        ;;
    4)
        CRON_SCHEDULE="0 8-18/2 * * *"
        SCHEDULE_DESC="every 2 hours during business hours"
        ;;
    5)
        read -p "Enter custom cron schedule (e.g., '0 */4 * * *'): " CRON_SCHEDULE
        SCHEDULE_DESC="custom schedule: $CRON_SCHEDULE"
        ;;
    *)
        echo -e "${RED}Invalid option selected${NC}"
        exit 1
        ;;
esac

echo
echo -e "${YELLOW}Database password setup:${NC}"
echo "The scraper requires a DB_PASSWORD environment variable."
echo "Current value: ${DB_PASSWORD:-<not set>}"
echo

if [ -z "$DB_PASSWORD" ]; then
    read -sp "Enter database password: " db_password
    echo
    
    # Add to user's shell profile
    SHELL_PROFILE=""
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_PROFILE="$HOME/.zshrc"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_PROFILE="$HOME/.bash_profile"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_PROFILE="$HOME/.bashrc"
    fi
    
    if [ -n "$SHELL_PROFILE" ]; then
        echo "export DB_PASSWORD=\"$db_password\"" >> "$SHELL_PROFILE"
        echo -e "${GREEN}Added DB_PASSWORD to $SHELL_PROFILE${NC}"
        echo -e "${YELLOW}Please run: source $SHELL_PROFILE${NC}"
    else
        echo -e "${YELLOW}Please manually add this to your shell profile:${NC}"
        echo "export DB_PASSWORD=\"$db_password\""
    fi
else
    echo -e "${GREEN}DB_PASSWORD is already set${NC}"
fi

echo
echo -e "${YELLOW}Setting up cron job...${NC}"

# Create the cron job entry
CRON_ENTRY="$CRON_SCHEDULE $WRAPPER_SCRIPT"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "$WRAPPER_SCRIPT"; then
    echo -e "${YELLOW}Cron job already exists. Updating...${NC}"
    # Remove existing entry and add new one
    (crontab -l 2>/dev/null | grep -v "$WRAPPER_SCRIPT"; echo "$CRON_ENTRY") | crontab -
else
    # Add new cron job
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
fi

echo -e "${GREEN}Cron job installed successfully!${NC}"
echo "Schedule: $SCHEDULE_DESC"
echo "Command: $CRON_ENTRY"
echo

# Test the setup
echo -e "${YELLOW}Testing the setup...${NC}"
if "$WRAPPER_SCRIPT" --test; then
    echo -e "${GREEN}Test passed! The scraper should run correctly.${NC}"
else
    echo -e "${RED}Test failed! Please check the configuration.${NC}"
    exit 1
fi

echo
echo -e "${GREEN}Setup complete!${NC}"
echo
echo -e "${YELLOW}Useful commands:${NC}"
echo "View cron jobs:     crontab -l"
echo "Edit cron jobs:     crontab -e"
echo "Remove cron jobs:   crontab -r"
echo "Check logs:         tail -f $PROJECT_DIR/logs/scraper.log"
echo "Monitor scraper:    $SCRIPTS_DIR/monitor_scraper.sh"
echo
echo -e "${YELLOW}Note:${NC} On macOS, you may need to grant Full Disk Access to Terminal"
echo "in System Preferences > Security & Privacy > Privacy > Full Disk Access"